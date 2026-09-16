#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${ROOT}/deploy"
ENV_FILE="${DEPLOY}/.env.dev"
COMPOSE="${DEPLOY}/docker-compose.dev.yml"
COMPOSE_CMD=(docker compose --env-file "${ENV_FILE}" -p pulsedeck-dev -f "${COMPOSE}")

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[ERROR] Missing ${ENV_FILE} — copy deploy/example/.env.dev.example" >&2
    exit 1
fi

"${COMPOSE_CMD[@]}" up -d

if "${ROOT}/scripts/check_css_watch.sh"; then
    echo "[CSS] Watcher already running"
else
    exec "${ROOT}/css_watcher.sh"
fi
