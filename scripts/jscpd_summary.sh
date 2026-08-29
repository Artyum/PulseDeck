#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

node_modules/.bin/jscpd --no-colors --no-tips 2>&1 | awk '/^┌/{p=1} p'
exit "${PIPESTATUS[0]}"
