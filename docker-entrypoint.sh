#!/bin/sh
# docker-entrypoint.sh — adjusts appuser/appgroup UID/GID to match the host
# user, then drops privileges and executes the main process.
#
# Environment variables:
#   PUID  — target user  ID (default: 1000)
#   PGID  — target group ID (default: 1000)
#
# This pattern (popularised by LinuxServer.io) ensures that files written to
# bind-mounted volumes have the same ownership as the host user, avoiding
# "permission denied" errors and root-owned files on the host.

set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Validate that PUID and PGID are positive integers and not root (0).
# Running the application as root defeats the entire privilege-drop mechanism.
case "$PUID" in
  ''|*[!0-9]*) echo "[entrypoint] ERROR: PUID must be a positive integer, got: '$PUID'" >&2; exit 1 ;;
esac
case "$PGID" in
  ''|*[!0-9]*) echo "[entrypoint] ERROR: PGID must be a positive integer, got: '$PGID'" >&2; exit 1 ;;
esac
if [ "$PUID" -eq 0 ] || [ "$PGID" -eq 0 ]; then
    echo "[entrypoint] ERROR: Running as root (PUID=0 or PGID=0) is not allowed." >&2
    exit 1
fi

echo "[entrypoint] Running as PUID=${PUID} PGID=${PGID}"

# Re-map the group and user to the requested IDs.
groupmod -o -g "${PGID}" appgroup
usermod  -o -u "${PUID}" appuser

# Ensure the data directory exists and is owned by the mapped user.
mkdir -p /app/data/traces
chown -R appuser:appgroup /app/data

# Hand off to the real command (CMD from Dockerfile) running as appuser.
exec gosu appuser "$@"
