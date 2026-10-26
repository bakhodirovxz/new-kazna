#!/usr/bin/env bash
# Repo darajasidagi skanerlar (spec 10): gitleaks (butun tarix), semgrep, hadolint.
set -euo pipefail
cd "$(dirname "$0")/.."
TOOLS=(docker compose -f deploy/compose.tools.yml run --rm -T)
echo "== gitleaks"; "${TOOLS[@]}" gitleaks
echo "== semgrep";  "${TOOLS[@]}" semgrep
echo "== hadolint"; "${TOOLS[@]}" hadolint
echo "check-repo: OK"
