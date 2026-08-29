#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${ROOT}/deploy"
ENV_FILE="${DEPLOY}/.env.dev"
COMPOSE="${DEPLOY}/docker-compose.dev.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[BLAD] Brak ${ENV_FILE} — skopiuj deploy/.env.dev.example" >&2
    exit 1
fi

if [[ $# -eq 0 ]]; then
    set -- tests/ -v --tb=line --color=yes --cov=app --cov-report=term-missing
fi

docker compose --env-file "${ENV_FILE}" -p pulsedeck-dev -f "${COMPOSE}" run --rm --no-deps \
    --entrypoint /bin/sh web -lc 'pip install -q -r requirements-dev.txt && python -m pytest "$@"' \
    test-runner "$@"
