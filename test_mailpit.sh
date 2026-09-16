#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${ROOT}/deploy"
ENV_FILE="${DEPLOY}/.env.dev"
RECIPIENT="${1:-test@pulsedeck.local}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[ERROR] Missing ${ENV_FILE} — copy deploy/example/.env.dev.example" >&2
    exit 1
fi

exec docker compose --env-file "${ENV_FILE}" -p pulsedeck-dev \
    -f "${DEPLOY}/docker-compose.dev.yml" run --rm --no-deps \
    --entrypoint python web scripts/test_smtp.py --mailpit \
    --smtp-server 192.168.50.50 --smtp-port 1025 "${RECIPIENT}"
