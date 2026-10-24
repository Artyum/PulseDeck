#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"

copy_if_newer() {
    src="$1"
    dest="$2"
    label="$3"
    if [ ! -f "${src}" ]; then
        echo "[ERROR] Missing ${src} — run npm ci" >&2
        exit 1
    fi
    mkdir -p "$(dirname "${dest}")"
    if [ ! -f "${dest}" ] || [ "${src}" -nt "${dest}" ]; then
        cp "${src}" "${dest}"
        echo "[VENDOR] Copied ${label}"
    else
        echo "[VENDOR] ${label} is up to date"
    fi
}

copy_if_newer \
    "${ROOT}/node_modules/@alpinejs/csp/dist/cdn.min.js" \
    "${ROOT}/frontend/static/vendor/alpine.min.js" \
    "alpine.min.js"

copy_if_newer \
    "${ROOT}/node_modules/htmx.org/dist/htmx.min.js" \
    "${ROOT}/frontend/static/vendor/htmx.min.js" \
    "htmx.min.js"
