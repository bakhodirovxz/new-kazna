#!/usr/bin/env bash
# E2E: dev stack ishlab turgan bo'lishi kerak (docker compose -f deploy/compose.yml up -d --build).
# Limit: login 10/min va MFA 20/min (IP bo'yicha) — to'liq yugurish 6 login ishlatadi; ~60 s ichida qayta
# yugurtirsangiz 429 chiqishi mumkin: bir daqiqa kuting, testni zaiflashtirmang.
# Foydalanish: scripts/e2e.sh [playwright argumentlari], masalan: scripts/e2e.sh --project=desktop-1440
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose -f deploy/compose.yml exec -T api python -m app.devtools seed-e2e
docker compose -f deploy/compose.frontend.yml run --rm e2e \
  sh -c 'npm ci && npx tsc --noEmit -p . && npx playwright test "$@"' e2e "$@"
