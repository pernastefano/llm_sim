# ── Build stage ───────────────────────────────────────────────────────────────
# Using python:3.11-slim to keep the image small.
FROM python:3.11-slim

# Metadata
LABEL description="LLM Simulation Demo — educational LLM pipeline simulator"

WORKDIR /app

# Install system packages:
#   gosu — drop-privileges helper used by docker-entrypoint.sh
#   (shadow-utils / passwd already present for usermod/groupmod in slim)
RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first so Docker can cache this layer
# independently of the application code.
# Use requirements.lock (exact pinned versions) for reproducible production
# builds.  Regenerate it with: pip freeze > requirements.lock
COPY requirements.lock requirements.txt ./
RUN pip install --no-cache-dir -r requirements.lock

# Copy the rest of the project
COPY . .

# ── Security: create the unprivileged user the app will run as ────────────────
# The actual UID/GID are remapped at runtime by docker-entrypoint.sh
# to match the host user (via PUID / PGID env vars).
RUN addgroup --system appgroup \
 && adduser  --system --ingroup appgroup --no-create-home appuser \
 && chmod +x /app/docker-entrypoint.sh

# ── Private data directory (traces + audit log — not served by Flask) ─────────
RUN mkdir -p /app/data/traces && chown -R appuser:appgroup /app/data

# ── Default behaviour ─────────────────────────────────────────────────────────
# The entrypoint remaps PUID/PGID, then starts Gunicorn as appuser.
#
# Configuration is loaded from config/.env (see config/.env.example).
#
# Environment variables:
#   PUID                  — host user  ID to run as (default: 1000)
#   PGID                  — host group ID to run as (default: 1000)
#   SECRET_KEY            — required in production for stable session cookies
#   SESSION_COOKIE_SECURE — set to "true" when served over HTTPS
#
# Override CMD to use the CLI instead:
#   docker run --rm -v $(pwd)/data:/app/data llm-sim python main.py "your query"

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/')" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "--timeout", "120", "--access-logfile", "-", "server:app"]
