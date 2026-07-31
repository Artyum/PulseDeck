#!/bin/sh
set -e

[ -z "${DATABASE_URL:-}" ] && echo "DATABASE_URL is required" >&2 && exit 1

exec python -m app.workers.mail
