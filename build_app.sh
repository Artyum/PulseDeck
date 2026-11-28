#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${ROOT}/deploy/build.sh" "${@}"
"${ROOT}/restart_app.sh"
