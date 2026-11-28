#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "${ROOT}/../sync-env/sync_env.py" \
  "${ROOT}/deploy/.env.dev" \
  "${ROOT}/deploy/example/.env.dev.example" \
  "${ROOT}/deploy/example/.env.preprod.example" \
  "${ROOT}/deploy/example/.env.prod.example"
