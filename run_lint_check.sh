#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"
LOG="${ROOT}/report/lint_check.log"
TOTAL=10
VENV="${ROOT}/.venv"
mkdir -p report

export NO_COLOR=1 FORCE_COLOR=0 TERM=dumb CI=1 LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8
export TMPDIR="${TMPDIR:-/tmp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

if [[ ! -x "${VENV}/bin/python" ]]; then
    echo "[BLAD] Brak .venv — utworz: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt" >&2
    exit 1
fi
export PATH="${VENV}/bin:${PATH}"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "[BLAD] Brak node/npm — zainstaluj Node.js (np. Node 22)" >&2
    exit 1
fi
if [[ ! -d node_modules ]]; then
    echo "[BLAD] Brak node_modules — uruchom: npm ci" >&2
    exit 1
fi

"${VENV}/bin/pip" install -q -r requirements-dev.txt

echo ""
echo "============ LINT CHECK (PulseDeck) ============"
echo ""

: > "${LOG}"
{
    echo "========================================"
    echo " LINT CHECK - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    echo ""
} >> "${LOG}"

results=()

run_step() {
    local n="$1"
    local title="$2"
    shift 2
    echo "[Krok ${n}/${TOTAL}] ${title}..."
    {
        echo "--- Krok ${n}/${TOTAL}: ${title} ---"
        date '+%Y-%m-%d %H:%M:%S'
        echo ""
    } >> "${LOG}"
    if "$@" >> "${LOG}" 2>&1; then
        results+=("0")
    else
        results+=("1")
    fi
    {
        echo ""
        echo "========================================"
        echo ""
    } >> "${LOG}"
}

run_djlint_reformat() {
    set +e
    djlint frontend/templates/ --reformat --quiet
    local status=$?
    set -e
    [[ "${status}" -eq 0 || "${status}" -eq 1 ]]
}

run_step 1 "ruff format" ruff format . --color=never
run_step 2 "djlint --reformat" run_djlint_reformat
run_step 3 "npm run format" npm run format
run_step 4 "ruff check --fix-only --show-fixes" ruff check . --fix-only --show-fixes --color=never
run_step 5 "ruff check" ruff check . --output-format=concise --color=never
run_step 6 "basedpyright" basedpyright --pythonpath "${VENV}/bin/python" app alembic scripts tests
run_step 7 "djlint --lint" djlint frontend/templates/ --lint
run_step 8 "npm run format:check" npm run format:check
run_step 9 "npm run lint:css" npm run lint:css
run_step 10 "jscpd" bash scripts/jscpd_summary.sh

echo ""
echo "============ PODSUMOWANIE ============"
echo ""

any_fail=0
for i in "${!results[@]}"; do
    step_no=$((i + 1))
    if [[ "${results[$i]}" -eq 0 ]]; then
        echo "  [${step_no}] PASS"
    else
        echo "  [${step_no}] FAIL"
        any_fail=1
    fi
done

echo ""
echo "  Log: ${LOG}"
echo ""

{
    echo ""
    echo "========================================"
    echo " PODSUMOWANIE"
    echo "========================================"
    echo ""
} >> "${LOG}"

for i in "${!results[@]}"; do
    step_no=$((i + 1))
    if [[ "${results[$i]}" -eq 0 ]]; then
        echo "  [${step_no}] PASS" >> "${LOG}"
    else
        echo "  [${step_no}] FAIL" >> "${LOG}"
    fi
done

if [[ "${any_fail}" -ne 0 ]]; then
    echo "[BLAD] Niektore kroki zakonczone bledem — sprawdz log."
    exit 1
fi

echo "[OK] Wszystkie kroki zakonczone pomyslnie."
