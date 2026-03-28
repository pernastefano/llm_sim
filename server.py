"""
server.py — Flask web server for the LLM Simulation Demo.

Session model
─────────────
Every browser receives an anonymous session cookie (UUID) on first visit.
No login is required.  All pipeline state is isolated per session:

  • The execution trace is saved to  data/traces/<session_id>.json
  • Every query is appended to       data/audit.jsonl

Both paths live inside data/ which Flask never serves — they are only
written and read programmatically.

Routes
──────
  GET  /                → main query UI   (ui/index.html)
  POST /run             → run the pipeline, return structured JSON
  GET  /trace           → Trace Viewer page  (ui/viewer.html)
  GET  /about           → About page
  GET  /llm_trace.json  → return the caller's own session trace (private)

Production (Gunicorn, 4 workers)
────────────────────────────────
  gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 120 server:app

Required env vars for production:
  SECRET_KEY            — stable random key shared across all workers
  SESSION_COOKIE_SECURE — set to "true" when served over HTTPS
"""
from __future__ import annotations

import argparse
import collections
import fcntl
import json
import logging
import os
import secrets
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Load config/.env (development fallback) ───────────────────────────────────
# In production (Docker / docker-compose) variables are injected directly into
# the process environment, so load_dotenv will not override them (override=False).
# In local development, config/.env is read automatically so you don't need to
# set environment variables by hand.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).parent / "config" / ".env", override=False)

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask import session as flask_session

from src.pipeline import LLMPipeline

# ── Directory layout ──────────────────────────────────────────────────────────
_ROOT       = Path(__file__).parent
_UI_DIR     = _ROOT / "ui"
_DATA_DIR   = _ROOT / "data"
_TRACES_DIR = _DATA_DIR / "traces"
_AUDIT_PATH = _DATA_DIR / "audit.jsonl"

# Private data directories — created at import time so all gunicorn workers
# see them immediately, even when forked after the master process.
_TRACES_DIR.mkdir(parents=True, exist_ok=True)

# ── App factory ───────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=None)

# ── Secret key ────────────────────────────────────────────────────────────────
# In production all gunicorn workers must share the same key so that a cookie
# signed by worker A can be verified by worker B.  Supply it via SECRET_KEY.
_WEAK_KEY_SENTINEL = "change-me-in-production"
_env_key = os.environ.get("SECRET_KEY")
if _env_key:
    if _env_key == _WEAK_KEY_SENTINEL:
        # Refuse to start with the well-known placeholder value.  An attacker
        # who knows this string can forge arbitrary session cookies.
        raise RuntimeError(
            "FATAL: SECRET_KEY is still set to the default placeholder value "
            "'change-me-in-production'.  This key is publicly known and must be "
            "replaced before deployment.  Generate a secure key with:\n"
            "  python3 -c 'import secrets; print(secrets.token_hex(32))'\n"
            "and set it in config/.env (or as an environment variable)."
        )
    app.secret_key = _env_key
else:
    app.secret_key = secrets.token_hex(32)
    logging.getLogger(__name__).warning(
        "SECRET_KEY env var not set — using a randomly generated key. "
        "Sessions will be invalidated on every restart and will NOT be "
        "consistent across multiple Gunicorn workers. "
        "Set SECRET_KEY in production."
    )

# ── Session cookie config ─────────────────────────────────────────────────────
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set SESSION_COOKIE_SECURE=true in production (requires HTTPS).
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
)

# ── Request body size limit ───────────────────────────────────────────────────
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024  # 8 KB

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)


# ── Audit log (thread-safe + multi-process-safe) ──────────────────────────────
# Uses threading.Lock (within one worker) and fcntl.flock (across workers).
_audit_lock = threading.Lock()


def _audit(record: dict) -> None:
    """Append one JSON record to the private audit log.  Never raises."""
    try:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with _audit_lock:
            with _AUDIT_PATH.open("a", encoding="utf-8") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                try:
                    fh.write(line)
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception as exc:  # noqa: BLE001
        _log.error("Audit log write failed: %s", exc)


# ── Per-IP sliding-window rate limiter ────────────────────────────────────────
_rate_lock = threading.Lock()
_rate_store: dict[str, collections.deque] = {}
_RATE_WINDOW  = 60      # seconds
_RATE_LIMIT   = 30      # max requests per window per IP
# Hard cap on tracked IPs to prevent memory exhaustion from spoofed source
# addresses.  When the cap is reached the oldest entry is evicted first.
_RATE_MAX_IPS = 10_000


def _is_rate_limited(ip: str) -> bool:
    """Return True if *ip* has exceeded the allowed request rate."""
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW
    with _rate_lock:
        dq = _rate_store.get(ip)
        if dq is None:
            # Evict oldest entry when the store is full to bound memory usage.
            if len(_rate_store) >= _RATE_MAX_IPS:
                oldest_ip = next(iter(_rate_store))
                del _rate_store[oldest_ip]
            dq = collections.deque()
            _rate_store[ip] = dq
        # Evict timestamps older than the window.
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _RATE_LIMIT:
            return True
        dq.append(now)
        return False


# ── Session helpers ───────────────────────────────────────────────────────────

def _get_or_create_session_id() -> str:
    """
    Return the caller's session ID, creating a new UUID if this is their
    first visit.  The ID is stored in Flask's signed session cookie.
    """
    if "sid" not in flask_session:
        flask_session["sid"] = str(uuid.uuid4())
    return flask_session["sid"]  # type: ignore[return-value]


def _trace_path_for(session_id: str) -> Path:
    """Return the private trace-file path for *session_id*.

    The session ID is a UUID — only hex digits and hyphens are kept in
    the filename to prevent any path-traversal attempts.
    """
    safe_id = "".join(c for c in session_id if c in "0123456789abcdef-")
    return _TRACES_DIR / f"{safe_id}.json"


# ── Security headers ──────────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response: object) -> object:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # NOTE: 'unsafe-inline' is needed because all JS/CSS is currently inline.
    # To remove it: move scripts/styles to external files and use CSP nonces.
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "base-uri 'none'; "
        "form-action 'self'"
    )
    # HSTS: only set when the app is served over HTTPS (SESSION_COOKIE_SECURE=true).
    # max-age=63072000 = 2 years, as recommended by hstspreload.org.
    if app.config.get("SESSION_COOKIE_SECURE"):
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
    # Restrict access to sensitive browser APIs that this app does not use.
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), "
        "payment=(), usb=(), bluetooth=()"
    )
    response.headers.pop("Server", None)
    return response


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index() -> object:
    _get_or_create_session_id()   # ensure the cookie is issued on first visit
    return send_from_directory(str(_UI_DIR), "index.html")


@app.route("/trace")
def trace_viewer() -> object:
    _get_or_create_session_id()
    return send_from_directory(str(_UI_DIR), "viewer.html")


@app.route("/about")
def about() -> object:
    return send_from_directory(str(_UI_DIR), "about.html")


@app.route("/llm_trace.json")
def trace_json() -> object:
    """Return the execution trace for the current user's session only."""
    sid = _get_or_create_session_id()
    path = _trace_path_for(sid)
    if not path.exists():
        return jsonify({"error": "No trace yet — run a query first."}), 404
    return send_file(str(path), mimetype="application/json")


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/run", methods=["POST"])
def run_pipeline() -> object:
    """
    Execute the LLM pipeline for the current user's query.

    Expects JSON body: { "query": "..." }

    Returns structured data so the UI can display:
    - tool badge + output (if a tool was called)
    - tokens with per-token probabilities (for animated display)
    - total trace step count
    """
    # ── Rate limiting (per client IP) ────────────────────────────────────────
    # ── Rate limiting ────────────────────────────────────────────────────────
    client_ip = request.remote_addr or "unknown"
    if _is_rate_limited(client_ip):
        return jsonify({"error": "Too many requests. Please try again later."}), 429

    # ── Session ──────────────────────────────────────────────────────────────
    sid = _get_or_create_session_id()

    # ── Input validation ─────────────────────────────────────────────────────
    body = request.get_json(silent=True) or {}
    query = str(body.get("query", "")).strip()

    if not query:
        return jsonify({"error": "Query cannot be empty."}), 400
    if len(query) > 500:
        return jsonify({"error": "Query is too long (max 500 characters)."}), 400

    try:
        # LLMPipeline is stateless — safe to instantiate per-request even with
        # concurrent workers; no shared mutable state.
        pipeline = LLMPipeline()
        result = pipeline.run(query)

        # Save trace to the session-private file (not accessible from the web).
        trace_path = _trace_path_for(sid)
        result.trace.save(str(trace_path))

        # ── Extract token-level data for the animated display ────────────────
        gen_steps = [
            s for s in result.trace.steps
            if s.name.startswith("generation_step_")
        ]
        tokens      = [s.data["selected_token"]       for s in gen_steps]
        token_probs = [s.data["selected_probability"]  for s in gen_steps]

        # ── Extract tool info from the agent reasoning step ──────────────────
        agent_step = next(
            (s for s in result.trace.steps if s.name == "agent_reasoning"), None
        )
        tool_used: str | None = None
        tool_output: str | None = None
        if agent_step:
            tool_used = agent_step.data.get("tool_used")
            tr = agent_step.data.get("tool_result")
            if tr and tr.get("success"):
                tool_output = tr.get("output")

        # ── Audit log ────────────────────────────────────────────────────────
        _audit({
            "ts":         time.time(),
            "session_id": sid,
            "ip":         client_ip,
            "query":      query,
            "tool_used":  tool_used,
            "answer":     result.final_answer,
        })

        return jsonify({
            "query":       query,
            "tool_used":   tool_used,
            "tool_output": tool_output,
            "tokens":      tokens,
            "token_probs": token_probs,
            "total_steps": len(result.trace.steps),
        })

    except Exception as exc:  # noqa: BLE001
        _log.error(
            "Pipeline error — session=%s query=%r: %s",
            sid, query[:80], exc, exc_info=True,
        )
        return jsonify({"error": "An internal error occurred. Please try again."}), 500


# ── Entry point (development only) ────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM Simulation Web Server")
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind address (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=5000,
        help="Port (default: 5000)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    base = f"http://{args.host}:{args.port}"
    print("=" * 56)
    print("  LLM Simulation — Web Server  (dev mode)")
    print("=" * 56)
    print(f"  Web UI     : {base}/")
    print(f"  Trace view : {base}/trace")
    print(f"  Audit log  : {_AUDIT_PATH}")
    print(f"  Traces dir : {_TRACES_DIR}")
    print("=" * 56)
    print("  For production use Gunicorn:")
    print("  gunicorn --workers 4 --bind 0.0.0.0:5000 server:app")
    print("=" * 56)
    app.run(host=args.host, port=args.port, debug=False)
