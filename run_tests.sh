#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${ROOT}/deploy"
ENV_FILE="${DEPLOY}/.env.dev"
COMPOSE="${DEPLOY}/docker-compose.dev.yml"
DEFAULT_PYTEST_OPTS=(-v --tb=line --color=yes --cov=app --cov-report=term-missing)

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[ERROR] Missing ${ENV_FILE} — copy deploy/example/.env.dev.example" >&2
    exit 1
fi

cd "${ROOT}"

STAGED=0
ARGS=()
for arg in "$@"; do
    if [[ "${arg}" == "--staged" ]]; then
        STAGED=1
    else
        ARGS+=("${arg}")
    fi
done

if [[ ${STAGED} -eq 1 ]]; then
    mapfile -t tests < <(git diff --cached --name-only --diff-filter=ACMR -- ':(glob)tests/**/test_*.py')
    if [[ ${#tests[@]} -eq 0 ]]; then
        echo "[ERROR] No staged test files (tests/**/test_*.py)" >&2
        exit 1
    fi
    printf '  %s\n' "${tests[@]}"
    echo ""
    if [[ ${#ARGS[@]} -eq 0 ]]; then
        set -- "${tests[@]}" "${DEFAULT_PYTEST_OPTS[@]}"
    else
        set -- "${tests[@]}" "${ARGS[@]}"
    fi
else
    set -- "${ARGS[@]+"${ARGS[@]}"}"
    if [[ $# -eq 0 ]]; then
        set -- tests/ "${DEFAULT_PYTEST_OPTS[@]}"
    fi
fi

docker compose --env-file "${ENV_FILE}" -p pulsedeck-dev -f "${COMPOSE}" run --rm --no-deps \
    -e PIP_ROOT_USER_ACTION=ignore \
    --entrypoint /bin/sh web -lc 'pip install -q -r requirements-dev.txt && python -m pytest "$@"' \
    test-runner "$@"
