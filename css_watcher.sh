#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

if ! command -v npm >/dev/null 2>&1; then
    echo "[ERROR] npm not found — install Node.js (e.g. Node 22)" >&2
    exit 1
fi

if [[ ! -x node_modules/.bin/tailwindcss ]]; then
    echo "[NPM] Tailwind CLI missing — running npm ci..."
    npm ci
fi

if [[ ! -f frontend/static/vendor/alpine.min.js ]]; then
    "${ROOT}/scripts/vendor-static.sh"
fi

echo "[CSS] Tailwind watch — frontend/static/css/app.css (Ctrl+C to stop)"
exec npm run css:watch
