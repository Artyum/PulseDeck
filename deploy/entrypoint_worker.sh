#!/bin/sh
set -e

[ -z "${DATABASE_URL:-}" ] && echo "DATABASE_URL is required" >&2 && exit 1

_reload_on() {
  case "${WORKER_RELOAD:-${UVICORN_RELOAD:-}}" in
    true|1|yes|TRUE|YES) return 0 ;;
    *) return 1 ;;
  esac
}

if ! _reload_on; then
  exec python -m app.workers.mail
fi

dirs="${WORKER_RELOAD_DIRS:-${UVICORN_RELOAD_DIRS:-/app/app}}"
set -- watchfiles --filter python "python -m app.workers.mail"
for dir in $dirs; do
  [ -d "$dir" ] && set -- "$@" "$dir"
done
echo "Worker reload via watchfiles: app.workers.mail ($dirs)" >&2
exec "$@"
