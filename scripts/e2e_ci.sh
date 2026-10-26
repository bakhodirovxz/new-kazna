#!/usr/bin/env bash
# CI: toza dev stack + Playwright E2E (3-reja Task 18) har PR'da — 2/3-reja saboqi: unit testlar
# commit/render tartibi xatolarini yashirdi. Faqat bir martalik CI checkout'i uchun (dev: make e2e).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -e deploy/secrets ]; then
  echo "e2e-ci: deploy/secrets mavjud — faqat toza CI checkout'ida ishlaydi (dev'da: make e2e)" >&2
  exit 2
fi
if docker volume inspect ugekazna_db_data >/dev/null 2>&1; then
  echo "e2e-ci: host'da ugekazna stack bor (ugekazna_db_data) — down -v uni o'chirardi; alohida runner kerak" >&2
  exit 2
fi
unset COMPOSE_PROJECT_NAME   # compose.frontend.yml tashqi tarmog'i: ugekazna_edge
C=(docker compose -f deploy/compose.yml)
cleanup() {
  # Playwright konteyneri root — hisobotni runner foydalanuvchisiga qaytaramiz (shell runner'da git clean).
  if [ -d frontend/e2e/playwright-report ] || [ -d frontend/e2e/test-results ]; then
    docker compose -f deploy/compose.frontend.yml run --rm -T --no-deps e2e \
      sh -c "chown -R $(id -u):$(id -g) playwright-report test-results 2>/dev/null || true" >/dev/null 2>&1 || true
  fi
  "${C[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf deploy/secrets
}
trap cleanup EXIT
python3 scripts/gen_secrets.py >/dev/null
chmod 0444 deploy/secrets/*   # faqat CI: Linux'da uid 70/999/10001 konteynerlari o'qiy olsin
"${C[@]}" up -d --build
for _ in $(seq 1 120); do
  [ "$("${C[@]}" ps --format '{{.Health}}' api | tr -d '\r')" = healthy ] && break
  sleep 5
done
[ "$("${C[@]}" ps --format '{{.Health}}' api | tr -d '\r')" = healthy ] || { "${C[@]}" logs --tail=80; exit 1; }
scripts/e2e.sh
