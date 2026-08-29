#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.dev"
COMPOSE="${SCRIPT_DIR}/docker-compose.dev.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[BLAD] Brak ${ENV_FILE} — skopiuj deploy/.env.dev.example" >&2
    exit 1
fi

BUILD_ARGS=()
[[ "${NO_CACHE:-}" == "1" ]] && BUILD_ARGS+=(--no-cache)

docker compose --env-file "${ENV_FILE}" -p pulsedeck-dev -f "${COMPOSE}" \
    build "${BUILD_ARGS[@]}"
