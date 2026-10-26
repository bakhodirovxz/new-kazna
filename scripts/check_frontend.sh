#!/usr/bin/env bash
# Frontend darvozalari (spec 10): tsc + eslint + vitest (npm run check) va npm audit (prod bog'liqliklar).
set -euo pipefail
cd "$(dirname "$0")/.."
NODE=(docker compose -f deploy/compose.frontend.yml run --rm -T node)
"${NODE[@]}" npm ci --ignore-scripts
echo "== tsc + eslint + vitest"; "${NODE[@]}" npm run check
echo "== npm audit";             "${NODE[@]}" npm audit --omit=dev --audit-level=high
echo "check-frontend: OK"
