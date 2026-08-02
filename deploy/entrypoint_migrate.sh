#!/bin/sh
set -e

[ -z "${DATABASE_URL:-}" ] && echo "DATABASE_URL is required" >&2 && exit 1

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

exec python -m app.bootstrap
