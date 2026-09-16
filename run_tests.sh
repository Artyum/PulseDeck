#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"
VENV="${ROOT}/.venv"
DEFAULT_PYTEST_OPTS=(-v --tb=line --color=yes --cov=app --cov-report=term-missing)

if [[ ! -x "${VENV}/bin/python" ]]; then
    echo "[ERROR] Missing .venv — create: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt" >&2
    exit 1
fi

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

exec "${VENV}/bin/python" -m pytest "$@"
