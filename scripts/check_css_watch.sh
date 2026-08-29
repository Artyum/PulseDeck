#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pgrep -f "tailwindcss.*${ROOT}/frontend/static/css/tailwind.css.*--watch" >/dev/null 2>&1
