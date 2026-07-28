#!/bin/sh
set -e

[ -z "${DATABASE_URL:-}" ] && echo "DATABASE_URL is required" >&2 && exit 1
[ -z "${STORAGE_SECRET:-}" ] && echo "STORAGE_SECRET is required" >&2 && exit 1

MAX_RETRIES="${ALEMBIC_MAX_RETRIES:-20}"
RETRY_DELAY="${ALEMBIC_RETRY_DELAY_SECONDS:-3}"
ATTEMPT=1

until alembic upgrade head; do
  if [ "$ATTEMPT" -ge "$MAX_RETRIES" ]; then
    echo "alembic upgrade head failed after ${ATTEMPT} attempts" >&2
    exit 1
  fi
  echo "alembic upgrade head failed (attempt ${ATTEMPT}/${MAX_RETRIES}); retrying in ${RETRY_DELAY}s..." >&2
  ATTEMPT=$((ATTEMPT + 1))
  sleep "$RETRY_DELAY"
done

HOST="${UVICORN_HOST:-0.0.0.0}"
PORT="${UVICORN_PORT:-8000}"
WORKERS="${UVICORN_WORKERS:-1}"

set -- app.main:fastapi_app --host "$HOST" --port "$PORT"

case "${UVICORN_PROXY_HEADERS}" in
    true|1|yes|TRUE|YES)
        set -- "$@" --proxy-headers --forwarded-allow-ips "${UVICORN_FORWARDED_ALLOW_IPS:-*}"
        ;;
esac

[ "$WORKERS" -gt 1 ] 2>/dev/null && set -- "$@" --workers "$WORKERS"
set -- "$@" --no-server-header

exec uvicorn "$@"
