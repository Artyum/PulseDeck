#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${ROOT}/deploy"

exec docker compose --env-file "${DEPLOY}/.env.dev" -p pulsedeck-dev \
    -f "${DEPLOY}/docker-compose.dev.yml" logs -f "$@"
