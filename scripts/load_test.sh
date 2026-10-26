#!/usr/bin/env bash
# Yuklama testi (TZ 9; docs/ops/load-test.md). Oldindan: dev stack ishlab turibdi
# (docker compose -f deploy/compose.yml up -d --build) va sintetik ma'lumot yuklangan (make seed-synthetic).
# k6: 20 → 50 → 100 VU. Natija: build/loadtest/report.md (protokol), build/loadtest/summary.json.
# Muhit: UGK_LOAD_DURATION — har bosqich davomiyligi (standart 3m; tez tekshiruv: 20s).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/loadtest
UGK_UID="$(id -u)"
UGK_GID="$(id -g)"
export UGK_UID UGK_GID
SESSIONS=build/loadtest/sessions.json
trap 'rm -f "$SESSIONS"' EXIT   # jonli sessiya tokenlari diskda qolmasin

docker compose -f deploy/compose.yml exec -T caddy cat /data/caddy/pki/authorities/local/root.crt \
  > build/loadtest/caddy-root.crt
docker compose -f deploy/compose.yml exec -T api python -m app.devtools seed-load --users 100 \
  | tr -d '\r' | tail -n 1 > "$SESSIONS"

set +e
docker compose -f deploy/compose.loadtest.yml run --rm -T k6 run /scripts/ugekazna.js
code=$?
set -e
echo "Protokol: build/loadtest/report.md (k6 chiqish kodi: $code; 99 — norma buzilgan)"
exit "$code"
