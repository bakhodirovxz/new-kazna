#!/usr/bin/env bash
# Caddyfile.prod xatti-harakati testi (7-vazifa). Caddy image — prod bilan bir xil digest.
# Oxirida: web image'da .git / *.map / src/ yo'qligi.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a
# shellcheck disable=SC1091
. deploy/images.lock.env
set +a
C=(docker compose -f deploy/tests/compose.caddy-test.yml)
trap '"${C[@]}" down -v --remove-orphans >/dev/null 2>&1 || true' EXIT
"${C[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${C[@]}" build certgen caddy
"${C[@]}" run --rm -T probe
"${C[@]}" run --rm -T probedev  # Caddyfile.dev: force-browsing (A7.R) — dev stack'siz
# Ichki healthcheck (compose.prod.yml bilan bir xil buyruq) haqiqatan ishlaydi.
[ "$("${C[@]}" exec -T caddy wget -qO- http://127.0.0.1:8081/health)" = ok ]   || { echo "FAIL ichki /health"; exit 1; }
echo "OK   ichki 8081/health"

# Image tarkibi: manba kodi, source map va git metama'lumotlari web image'ga tushmasligi shart.
leak=$(MSYS_NO_PATHCONV=1 docker run --rm --entrypoint sh ugekazna-web:caddytest -c \
  'find / -xdev \( -name .git -o -name "*.map" -o -path /srv/src -o -path "/srv/*/src" -o -path /app \) 2>/dev/null')
if [ -n "$leak" ]; then echo "FAIL web image'da ortiqcha fayllar:"; echo "$leak"; exit 1; fi
echo "OK   web image: .git, *.map, src/ yo'q"

