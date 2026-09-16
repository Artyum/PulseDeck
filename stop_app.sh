#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${ROOT}/deploy"
ENV_FILE="${DEPLOY}/.env.dev"
COMPOSE="${DEPLOY}/docker-compose.dev.yml"

if "${ROOT}/scripts/check_css_watch.sh"; then
    pkill -f "tailwindcss.*frontend/static/css/tailwind.css.*--watch" || true
    echo "[CSS] Watcher stopped"
fi

docker compose --env-file "${ENV_FILE}" -p pulsedeck-dev -f "${COMPOSE}" down --remove-orphans
