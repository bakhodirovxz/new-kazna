#!/usr/bin/env bash
# e2e/ tsc darvozasi: e2e eslint va asosiy tsc'dan tashqarida, shuning uchun alohida tekshiriladi.
# Foydalanish: scripts/e2e_typecheck.sh [e2e katalogi]  (standart: frontend/e2e). Xatoda noldan farqli kod.
# Variantlar (-v) xizmat nomidan OLDIN turishi shart; keyin — konteyner buyrug'i bo'lib qoladi.
# MSYS_NO_PATHCONV: Git Bash /e2e-src yo'lini buzmasligi uchun.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(cd "${1:-frontend/e2e}" && pwd)"
MSYS_NO_PATHCONV=1 docker compose -f deploy/compose.frontend.yml run --rm -T \
  -v "$DIR:/e2e-src:ro" node sh -c \
  'cp -r /e2e-src /tmp/e2e && cd /tmp/e2e && rm -rf node_modules && npm ci --ignore-scripts && npx tsc --noEmit -p .'
