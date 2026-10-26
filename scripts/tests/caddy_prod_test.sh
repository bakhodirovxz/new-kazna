#!/usr/bin/env bash
# Caddyfile.prod xatti-harakati testi (7-vazifa). Caddy image — prod bilan bir xil digest.
# Oxirida: web image'da .git / *.map / src/ yo'qligi va https://localhost:8443 dev Caddyfile'i
# (dev stack ishlab turgan bo'lsa) uchun force-browsing tekshiruvi.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a
# shellcheck disable=SC1091
. deploy/images.lock.env
set +a
C=(docker compose -f deploy/tests/compose.caddy-test.yml)
trap '"${C[@]}" down -v --remove-orphans >/dev/null 2>&1 || true' EXIT
"${C[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${C[@]}" build caddy
"${C[@]}" run --rm -T probe

# Image tarkibi: manba kodi, source map va git metama'lumotlari web image'ga tushmasligi shart.
leak=$(MSYS_NO_PATHCONV=1 docker run --rm --entrypoint sh ugekazna-web:caddytest -c \
  'find / -xdev \( -name .git -o -name "*.map" -o -path /srv/src -o -path "/srv/*/src" -o -path /app \) 2>/dev/null')
if [ -n "$leak" ]; then echo "FAIL web image'da ortiqcha fayllar:"; echo "$leak"; exit 1; fi
echo "OK   web image: .git, *.map, src/ yo'q"

# Dev Caddyfile (dev stack ishlab turgan bo'lsa): force-browsing yo'llari 404, SPA yo'li 200.
if curl -sk -o /dev/null --max-time 3 https://localhost:8443/; then
  for p in /.git/config /.git/HEAD /.env /.gitignore /deploy/compose.prod.yml \
           /backend/app/core/config.py /src/main.tsx /package.json /.DS_Store \
           /%2e%2e/etc/passwd /assets/../.git/config /api/v1/healthz /api/v1/readyz; do
    code=$(curl -sk --path-as-is -o /dev/null -w '%{http_code}' "https://localhost:8443$p")
    [ "$code" = 404 ] || { echo "FAIL dev $p -> $code"; exit 1; }
  done
  [ "$(curl -sk -o /dev/null -w '%{http_code}' https://localhost:8443/deep/link)" = 200 ] \
    || { echo "FAIL dev SPA fallback"; exit 1; }
  echo "OK   dev Caddyfile: force-browsing 404, SPA 200"
else
  echo "SKIP dev Caddyfile (https://localhost:8443 javob bermadi)"
fi
