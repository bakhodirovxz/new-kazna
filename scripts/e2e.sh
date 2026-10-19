#!/usr/bin/env bash
# E2E: dev stack ishlab turgan bo'lishi kerak (docker compose -f deploy/compose.yml up -d --build).
# Foydalanish: scripts/e2e.sh [playwright argumentlari], masalan: scripts/e2e.sh --project=desktop-1440
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose -f deploy/compose.yml exec -T api python -m app.devtools seed-e2e
docker compose -f deploy/compose.frontend.yml run --rm e2e \
  sh -c 'npm ci && npx tsc --noEmit -p . && npx playwright test "$@"' e2e "$@"
