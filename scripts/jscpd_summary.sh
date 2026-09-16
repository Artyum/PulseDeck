#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

out="$(mktemp)"
trap 'rm -f "$out"' EXIT

set +e
node_modules/.bin/jscpd --no-colors . >"$out" 2>&1
status=$?
set -e

if [[ "$status" -eq 0 ]] && grep -q '^┌' "$out"; then
  awk '/^┌/{p=1} p' "$out"
else
  cat "$out"
fi
exit "$status"
