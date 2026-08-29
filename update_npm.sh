#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

if ! command -v npm >/dev/null 2>&1; then
    echo "[BLAD] Brak npm — zainstaluj Node.js (np. Node 22)" >&2
    exit 1
fi

npm install
npm outdated || true
npm update
npm audit fix || true
npm prune
npm audit || true
"${ROOT}/scripts/vendor-static.sh"
npm run css:build:dev
npm run js:build
