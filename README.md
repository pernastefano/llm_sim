# 🧠 LLM-sim

A **clean, modular, educational Python project** that simulates the internal
behavior of a Large Language Model — including prompt construction, tokenization,
a reasoning agent with tool use, and token-by-token probabilistic generation.

The goal is **clarity and observability**, not realism.  Every step of the
pipeline is explicitly logged to a JSON trace that can be explored through two
different UIs.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [How the simulation works](#how-the-simulation-works)
- [Project structure](#project-structure)
- [Running the web UI](#running-the-web-ui)
- [Running the CLI](#running-the-cli)
- [Using the HTML viewer](#using-the-html-viewer)
- [Running with Docker](#running-with-docker)
- [Session isolation & audit log](#session-isolation--audit-log)
- [Configuration reference](#configuration-reference)

---

## Overview

```
User query  ←── typed in the browser
    │
    ▼  (POST /run)
server.py ─── LLM Pipeline ──────────────────────────────────┐
    │              │                                          │
    │         PromptBuilder ──► full prompt text              │
    │              │                                          │
    │         SimpleTokenizer ──► token IDs                  │
    │              │                                          │
    │         ReasoningAgent ──► tools ──► Calculator/Search  │
    │              │                                          │
    │         LLMCore ──► token-by-token generation           │
    │              │                                          │
    │         final answer  +  llm_trace.json ◄───────────────┘
    │
    ▼  (JSON response)
ui/index.html ── animated token display ── "View Trace" button
    │
    └──► ui/viewer.html?autoload  (full execution trace)
```

The entire pipeline is **observable**: every decision, probability table, and
tool call is captured in a structured JSON trace.

---

## Architecture

The project is split into small, single-responsibility modules:

| Module | Responsibility |
|---|---|
| `src/trace.py` | Append-only, JSON-serialisable execution trace |
| `src/prompt_builder.py` | Combine system + user text into a structured prompt |
| `src/tokenizer.py` | Whitespace + punctuation tokenizer with dynamic vocab |
| `src/llm_core.py` | Token-by-token generation: scoring, softmax, sampling |
| `src/tools.py` | Calculator (safe eval) and FakeSearch (in-memory KB) |
| `src/agent.py` | Reasoning layer: intent detection + tool dispatch |
| `src/pipeline.py` | Top-level orchestrator that wires all components |
| `main.py` | CLI entry point |
| `server.py` | Flask web server (query UI + trace API) |
| `ui/index.html` | Web UI: query form, animated token answer, trace link |
| `ui/viewer.html` | Zero-dependency static trace viewer |

**Key design decisions:**
- Components depend only on the `Trace` dataclass — never on each other directly.
- `LLMCore` is decoupled from the agent; it only receives a prompt string and
  a list of target tokens.
- Tools return a uniform `ToolResult` dataclass, making them trivially swappable.
- The tokenizer's vocabulary is dynamic: every new token is registered on demand.

---

## How the simulation works

### 1. Prompt construction
`PromptBuilder` wraps the user input and a fixed system prompt into a labelled
template (`[SYSTEM]`, `[USER]`, `[ASSISTANT]`).

### 2. Tokenization
`SimpleTokenizer` splits text on whitespace and punctuation using a regex, then
maps each surface form to an integer ID via a growing vocabulary dictionary.
`encode()` and `decode()` are exact inverses.

### 3. Reasoning (agent)
`ReasoningAgent` applies two heuristics in sequence:
1. **Math detection** — if the query contains an arithmetic expression and a
   trigger word ("calculate", "what is", …), the `CalculatorTool` is called.
2. **Factual detection** — if the query contains a question prefix ("what is",
   "explain", …), `FakeSearchTool` is called to look up a topic.

Every decision step is logged explicitly so users can follow the reasoning.

### 4. Token-by-token generation
`LLMCore.generate()` simulates the generation loop:
- For each target token, `top_k` candidates are drawn (target + random vocab words).
- Each candidate receives a **pseudo-random base score** plus a **repetition
  penalty** (tokens seen in the recent context window are penalised 75%).
- The target token receives a score boost (×2.8) so the demo stays coherent.
- **Temperature-scaled softmax** converts scores to a probability distribution.
- The full candidate table (token, score, probability) is logged to the trace,
  making the generation step fully transparent.

### 5. Final answer composition
The pipeline combines the tool output (if any) with the generated text into a
human-readable final answer.

---

## Project structure

```
llm_sim/
├── src/
│   ├── __init__.py
│   ├── trace.py            # TraceStep + Trace
│   ├── prompt_builder.py   # PromptBuilder
│   ├── tokenizer.py        # SimpleTokenizer
│   ├── llm_core.py         # LLMCore + GenerationConfig
│   ├── tools.py            # CalculatorTool + FakeSearchTool (AST-safe eval)
│   ├── agent.py            # ReasoningAgent
│   └── pipeline.py         # LLMPipeline
├── ui/
│   ├── index.html          # Web UI: query form + animated answer
│   ├── viewer.html         # Static HTML trace viewer
│   └── about.html          # How it works
├── data/                   # ← created at runtime, NOT served by Flask
│   ├── traces/             # Per-session execution traces (one JSON per user)
│   └── audit.jsonl         # Append-only JSONL audit log
├── main.py                 # CLI entry point
├── server.py               # Flask + Gunicorn web server
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Running the web UI

This is the **recommended** way to use the project.  Everything happens in the
browser: you type a query, watch the pipeline stages animate, see the answer
with colour-coded token probabilities, and then open the full execution trace in
one click.

### Prerequisites

```bash
cd llm_sim
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Start the server

```bash
# Development (single process, auto-reloads not active)
python server.py

# Production (Gunicorn, 4 parallel workers)
gunicorn --workers 4 --bind 127.0.0.1:5000 --timeout 120 server:app
```

Then open **http://localhost:5000/** in your browser.

```
  Web UI     : http://localhost:5000/
  Trace view : http://localhost:5000/trace
  Audit log  : data/audit.jsonl  (private — not accessible from browser)
```

Workflow:
1. Type any question (or pick an example chip) and click **Ask →**.
2. Watch the six pipeline stages complete one-by-one.
3. The answer appears with each token animated as a colour-coded pill showing
   its generation probability (🟢 ≥ 80% · 🟡 50–80% · 🔴 < 50%).
4. Click **🔍 View Execution Trace →** — the trace viewer opens in a new tab,
   already loaded with the latest trace.

---

## Running the CLI

The CLI is still available as a quick alternative.

### Install dependencies

```bash
cd llm_sim
# Optional: install dependencies for optional data analysis extensions
pip install -r requirements.txt
```

### Run the simulation

```bash
# Default query
python main.py

# Custom query
python main.py "What is 42 * 7 + 15?"
python main.py "Explain the transformer architecture"
python main.py "Calculate 100 / 4 + 3 * 2"
```

This writes `llm_trace.json` to the project root and prints the final answer.

---

## Using the HTML viewer

When using the web server (`python server.py`) the trace viewer is available
directly at **http://localhost:5000/trace** and loads automatically after each
query.

To use it standalone:

### Option A — Via the web server (recommended)

```bash
python server.py
```

Click **🔍 View Execution Trace →** in the main UI, or go to
`http://localhost:5000/trace` directly.

### Option B — Python HTTP server

```bash
# From the project root:
python main.py              # generate a trace first
python -m http.server 8000
```

Then open `http://localhost:8000/ui/viewer.html` and click
**⚡ Auto-load llm_trace.json**.

### Option C — Local file (no server needed)

Open `ui/viewer.html` in any browser, click **Browse file…** and select
`llm_trace.json`.  (Browser security blocks XHR on `file://` URLs, so the
file-picker method must be used.)

### Viewer features

- Collapsible step cards with step-type icons
- Colour-coded JSON syntax highlighting
- Inline probability bar charts for generation steps
- Human-readable reasoning trace for the agent step
- Filter bar to narrow down steps by name
- Drag-and-drop JSON file support

---

## Running with Docker

The **fastest way** to get started — no cloning or building required.  The
pre-built image is published to the GitHub Container Registry at
`ghcr.io/pernastefano/llm_sim`.

### Quick start with docker-compose (recommended)

Create a `docker-compose.yml` file anywhere on your machine with the following
content:

```yaml
services:
  llm-sim:
    image: ghcr.io/pernastefano/llm_sim:latest
    container_name: llm-sim
    ports:
      - "5000:5000"
    environment:
      - PUID=1000   # replace with your host UID: id -u
      - PGID=1000   # replace with your host GID: id -g
      - SECRET_KEY=change-me-to-a-random-secret
      # - SESSION_COOKIE_SECURE=true   # uncomment when behind HTTPS
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      test:
        - "CMD"
        - "python3"
        - "-c"
        - "import urllib.request; urllib.request.urlopen('http://localhost:5000/')"
      interval: 30s
      timeout: 5s
      start_period: 15s
      retries: 3
```

Then run:

```bash
# Pull the latest image and start the container
docker compose up -d

# Follow the logs
docker compose logs -f
```

Then open **http://localhost:5000/** in your browser.

> **`SECRET_KEY`** — replace `change-me-to-a-random-secret` with a real random
> value before going to production:
> ```bash
> python3 -c 'import secrets; print(secrets.token_hex(32))'
> ```

> **HTTPS in production** — put Nginx or Caddy in front of the container and
> set `SESSION_COOKIE_SECURE=true` in the `environment` block.

The container runs Gunicorn with 4 workers. PUID/PGID are applied by the
entrypoint so that files written to `./data` are owned by your host user.

### Pull the image manually

```bash
docker pull ghcr.io/pernastefano/llm_sim:latest
```

### Run with `docker run` (no compose file)

```bash
mkdir -p data/traces

docker run --rm \
  -p 5000:5000 \
  -e PUID="$(id -u)" \
  -e PGID="$(id -g)" \
  -e SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  -v "$(pwd)/data":/app/data \
  ghcr.io/pernastefano/llm_sim:latest
```

### Run the CLI only

```bash
# Default query
docker run --rm -v "$(pwd)/data":/app/data ghcr.io/pernastefano/llm_sim:latest python main.py

# Custom query
docker run --rm -v "$(pwd)/data":/app/data ghcr.io/pernastefano/llm_sim:latest python main.py "What is an LLM?"
```

### Build from source (optional)

If you want to build the image yourself from the source code:

```bash
git clone https://github.com/pernastefano/llm_sim.git
cd llm_sim
docker compose up --build
```

---

## Session isolation & audit log

Every browser that connects to the server automatically receives an **anonymous
session cookie** (a UUID stored in a signed cookie — no login required).

### Per-user isolation

| Concern | How it is handled |
|---------|------------------|
| Concurrent users | Each request runs a fresh, stateless `LLMPipeline` in the Gunicorn worker that received it. No shared mutable state between sessions. |
| Trace separation | Each session's execution trace is saved to `data/traces/<session_id>.json`. User A can never see User B's trace. |
| Cookie integrity | The session cookie is signed with `SECRET_KEY` via Flask's `itsdangerous` HMAC. Tampering invalidates the cookie. |

### Audit log

Every submitted query is appended to `data/audit.jsonl` — a private,
line-delimited JSON file that Flask **never exposes** through any route.

Each record contains:

```jsonc
{
  "ts":         1743120000.0,    // Unix timestamp
  "session_id": "f47ac10b-...",  // anonymous UUID
  "ip":         "203.0.113.5",   // client IP
  "query":      "What is 42 * 7 + 15?",
  "tool_used":  "calculator",
  "answer":     "[Tool: calculator]\n309\n\n[Generated response]\nThe result is 309 ."
}
```

Writing is safe under concurrent access: both a `threading.Lock` (within one
Gunicorn worker) and `fcntl.flock` (across workers) are used.

### Required environment variable for production

```bash
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

All Gunicorn workers **must share the same key** so that session cookies signed
by worker A are still valid when the next request hits worker B.  
If `SECRET_KEY` is not set the server generates a random key at startup —
sessions survive within a single process but are invalidated on restart.

---

## Configuration reference

All configuration lives in `config/.env`.  Copy the template to get started:

```bash
cp config/.env.example config/.env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | _(random)_ | HMAC key for signing session cookies. **Must** be set and shared across all workers in production. |
| `SESSION_COOKIE_SECURE` | `false` | Set to `true` when serving over HTTPS to add the `Secure` flag to cookies. |
| `PUID` | `1000` | Host user ID the container process runs as (Docker only). |
| `PGID` | `1000` | Host group ID the container process runs as (Docker only). |

### How it is loaded

- **Docker / docker-compose**: `env_file: ./config/.env` in `docker-compose.yml` injects variables directly into the container environment _before_ the process starts. `python-dotenv` will not override them (`override=False`).
- **Local development**: `server.py` calls `load_dotenv("config/.env")` at startup — no manual `export` needed.

---

## Extending the project

- **Add a new tool**: create a class with a `.run(input: str) -> ToolResult` method
  in `src/tools.py`, then register it in `ReasoningAgent.__init__()`.
- **Change generation behaviour**: adjust `GenerationConfig` (temperature, top_k,
  seed) in `main.py` or pass a custom config to `LLMPipeline`.
- **Add knowledge base entries**: extend the `_KNOWLEDGE_BASE` dict in
  `src/tools.py`.
- **Add a new trace step**: call `trace.add(name, description, data)` from anywhere
  in the pipeline — it will automatically appear in the HTML viewer.
