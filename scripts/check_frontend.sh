#!/usr/bin/env bash
# Frontend darvozalari (spec 10): tsc + eslint + vitest (npm run check) va npm audit (prod bog'liqliklar).
set -euo pipefail
cd "$(dirname "$0")/.."
NODE=(docker compose -f deploy/compose.frontend.yml run --rm -T node)
"${NODE[@]}" npm ci --ignore-scripts
echo "== tsc + eslint + vitest"; "${NODE[@]}" npm run check
# e2e/ tsc va eslint'dan tashqarida (src/ gina) — spec'lar sintaksis/tip xatosi bilan kelmasin (r1 I3).
echo "== e2e tsc";               scripts/e2e_typecheck.sh
echo "== npm audit";             "${NODE[@]}" npm audit --omit=dev --audit-level=high
echo "check-frontend: OK"
