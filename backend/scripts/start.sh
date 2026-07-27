#!/usr/bin/env bash
#
# Production entrypoint for the single free Render Web Service.
#
# One container runs both the Dramatiq worker (background) and the FastAPI/Uvicorn API
# (foreground-supervised). This is the free-tier shape: Render's free plan gives one service, so
# the worker rides along with the API instead of being a separate paid Background Worker.
#
# Log streams are distinguishable: this script prefixes its own lines with "[start.sh]", the
# worker's log records carry "dramatiq..." logger names, and the API's carry "uvicorn"/"app..."
# names (see app/core/logging.py).
set -euo pipefail

log() { echo "[start.sh] $*"; }

# Schema migration runs before serving. Idempotent, so it is safe on every deploy/restart.
log "running database migrations (alembic upgrade head)"
python -m alembic upgrade head

# Worker in the background: same container consumes queued analyses.
log "starting dramatiq worker"
python -m dramatiq app.workers.main --processes 1 --threads 4 &
WORKER_PID=$!

# API in the background too, so this script supervises both and can forward shutdown to each.
log "starting uvicorn on port ${PORT:-8000}"
python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*" &
API_PID=$!

# On container stop (SIGTERM) or Ctrl-C, drain both processes cleanly.
shutdown() {
  log "shutdown signal received; stopping API and worker"
  kill -TERM "$API_PID" "$WORKER_PID" 2>/dev/null || true
}
trap shutdown TERM INT

# Block on the API. A worker crash must NOT take the whole free service down, so we wait on the
# API only; if the worker dies, the API keeps serving and analyses queue until the next deploy
# (visible in logs — no silent partial outage of the web tier).
set +e
wait "$API_PID"
API_STATUS=$?
set -e

log "uvicorn exited with status ${API_STATUS}; stopping worker"
kill -TERM "$WORKER_PID" 2>/dev/null || true
wait "$WORKER_PID" 2>/dev/null || true
exit "${API_STATUS}"
