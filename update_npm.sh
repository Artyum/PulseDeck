#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

if ! command -v npm >/dev/null 2>&1; then
    echo "[ERROR] npm not found — install Node.js (e.g. Node 22)" >&2
    exit 1
fi

if [[ ! -f package.json ]]; then
    echo "[ERROR] package.json not found" >&2
    exit 1
fi

if [[ ! -d node_modules ]]; then
    echo "[NPM] Installing dependencies (npm ci)..."
    npm ci
fi

echo "[NPM] Updating dependencies per package.json..."
npm update

echo "[NPM] Pruning unused dependencies..."
npm prune

echo "[FRONTEND] Vendor + CSS + editor..."
"${ROOT}/scripts/vendor-static.sh"
npm run css:build:dev
npm run js:build

echo
echo "[OK] Done. Bump major versions (outside ^/~) manually in package.json."
echo "     Audit: ./run_audit.sh   Check newer versions: npm outdated"

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git diff --quiet -- package-lock.json; then
        echo "[NPM] package-lock.json unchanged."
    else
        echo "[NPM] package-lock.json changed — review and commit."
    fi
fi
