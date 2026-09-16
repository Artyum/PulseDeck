#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

command -v docker >/dev/null || {
    echo "docker command not found." >&2
    exit 1
}

command -v trivy >/dev/null || {
    echo "trivy command not found." >&2
    exit 1
}

command -v jq >/dev/null || {
    echo "jq command not found." >&2
    exit 1
}

if [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

if ! "${PYTHON}" -c "import pip_audit" 2>/dev/null; then
    echo "[ERROR] pip-audit missing — install: ${PYTHON} -m pip install -r requirements-dev.txt" >&2
    exit 1
fi

"${PYTHON}" -m pip_audit -r requirements.txt

if ! npm audit --omit=dev --audit-level=high; then
    echo "[NPM] Vulnerabilities found. To fix intentionally: npm audit fix" >&2
    exit 1
fi

TRIVY_IMAGE="${TRIVY_IMAGE:-pulsedeck:latest}"

docker build \
    --file deploy/Dockerfile \
    --tag "${TRIVY_IMAGE}" \
    .

TRIVY_JSON="$(mktemp)"
trap 'rm -f "${TRIVY_JSON}"' EXIT

trivy image \
    --format json \
    --exit-code 0 \
    --ignore-unfixed \
    --severity HIGH,CRITICAL \
    "${TRIVY_IMAGE}" \
    > "${TRIVY_JSON}"

echo
echo "Trivy vulnerabilities:"
printf "%-20s %-10s %-12s %-12s\n" \
    "Library" "Severity" "Installed" "Fixed"

jq -r '
    .Results[]?.Vulnerabilities[]? |
    [
        .PkgName,
        .Severity,
        .InstalledVersion,
        (.FixedVersion // "-")
    ] |
    @tsv
' "${TRIVY_JSON}" |
while IFS=$'\t' read -r library severity installed fixed; do
    printf "%-20s %-10s %-12s %-12s\n" \
        "$library" "$severity" "$installed" "$fixed"
done

if jq -e '
    [.Results[]?.Vulnerabilities[]?] | length > 0
' "${TRIVY_JSON}" >/dev/null; then
    echo
    echo "[TRIVY] Found HIGH/CRITICAL vulnerabilities." >&2
    exit 1
fi

echo
echo "Security audit completed successfully."
