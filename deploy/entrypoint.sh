#!/bin/sh
set -e

[ -z "${DATABASE_URL:-}" ] && echo "DATABASE_URL is required" >&2 && exit 1
[ -z "${STORAGE_SECRET:-}" ] && echo "STORAGE_SECRET is required" >&2 && exit 1

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
