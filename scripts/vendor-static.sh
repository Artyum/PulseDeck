#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${ROOT}/node_modules/alpinejs/dist/cdn.min.js"
DEST="${ROOT}/frontend/static/vendor/alpine.min.js"

if [[ ! -f "${SOURCE}" ]]; then
    echo "[BLAD] Brak ${SOURCE} — uruchom npm ci" >&2
    exit 1
fi

mkdir -p "$(dirname "${DEST}")"
if [[ ! -f "${DEST}" || "${SOURCE}" -nt "${DEST}" ]]; then
    cp "${SOURCE}" "${DEST}"
    echo "[VENDOR] Skopiowano alpine.min.js"
else
    echo "[VENDOR] Alpine.js jest aktualny"
fi
