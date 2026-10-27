#!/usr/bin/env bash
# Zaxira/tiklash avtotesti (Docker; sekin — 10–25 daqiqa): make backup-selftest.
# Prod compose'ni alohida loyihada (ugekazna-selftest) sinov sirlari va `ci` profili bilan ko'taradi:
#  1) prod stack hardening bilan ishga tushadi (servislar healthy, migrate 0);
#  2) bo'sh repo: restore_test.sh → kod 3, vaqtinchalik klaster qolmaydi, last_restore_test = fail;
#  3) sintetik ma'lumot + prod API smoke (Caddy → api → Redis ACL/kesh, probe'lar yopiq, 80→308);
#  4) to'liq zaxira;  5) zaxiradan KEYIN yozuv + WAL arxivi;  6) restore_test.sh → ok;
#  7) tiklangan nusxada zaxiradan keyingi yozuv bor (WAL replay — RPO mexanizmi);
#  8) prod repo'da tiklangan klasterning timeline'i yo'q, pgbackrest check ok;
#  9) monitor.sh: sog' stack → 0; backup to'xtatilsa → 1.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
cd "$ROOT"
# Shell muhiti --env-file'dan ustun: prod host'dagi UGK_*/SMTP_* sinov stack'iga (prod sirlari, prod repo) o'tmasin.
for v in $(compgen -v UGK_) $(compgen -v SMTP_); do unset "$v"; done
VERSION=selftest
PROJECT=ugekazna-selftest
WORK="$ROOT/build/selftest"
VOLUME=ugekazna_selftest_repo
export UGK_PROJECT="$PROJECT" UGK_ENV_FILES="$WORK/selftest.env" UGK_LOG_DIR="$WORK/logs"
P=(docker compose -p "$PROJECT" -f deploy/compose.prod.yml --env-file "$WORK/selftest.env")
R=(docker compose -p "$PROJECT-restore" -f deploy/compose.restore.yml --env-file "$WORK/selftest.env")
CURL=(curl -s --cacert "$WORK/secrets/tls_cert.pem" --resolve ugk.selftest:18443:127.0.0.1)
IS_WIN=no
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) IS_WIN=yes; CURL+=(--ssl-no-revoke) ;; esac
# Windows (Schannel) curl HTTP javobidan keyin non-zero qaytarishi mumkin (sababi tasdiqlanmagan taxmin:
# TLS close_notify yo'q). Faqat Windows'da HTTP kodi mos kelsa kechiriladi; Linux'da fail-closed.
http_code() {
  local out rc=0
  out="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$@")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "curl chiqish kodi $rc (http $out)" >&2
    [ "$IS_WIN" = yes ] || out="curl-xato-$rc"
  fi
  printf '%s' "$out"
}

cleanup() {
  "${R[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  "${P[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  # Faqat aynan shu sinov papkasi (sinov sirlari 0444 qoladi — qoldirmaymiz).
  if [ -n "$WORK" ] && [ "$WORK" = "$ROOT/build/selftest" ]; then rm -rf "$WORK"; fi
}
step() { printf '\n######## %s\n' "$*"; }
die() { echo "SELFTEST XATO: $*" >&2; exit 1; }
wait_healthy() {
  for _ in $(seq 1 "$2"); do
    if [ "$("${P[@]}" ps --format '{{.Health}}' "$1" 2>/dev/null | tr -d '\r' | sed -n 1p)" = healthy ]; then
      return 0
    fi
    sleep 1
  done
  "${P[@]}" logs --tail=80 "$1" || true
  die "$1 $2 s ichida healthy bo'lmadi"
}
psql_prod() { "${P[@]}" exec -T db psql -U postgres -d ugekazna -tAc "$1" | tr -d '\r'; }

step "0. image'lar, sinov sirlari va sertifikat"
scripts/build_images.sh "$VERSION"
if [ -f "$WORK/selftest.env" ]; then cleanup; fi
trap cleanup EXIT
rm -rf "$WORK"
mkdir -p "$WORK/secrets" "$WORK/logs"
docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT/scripts:/s:ro" -v "$WORK/secrets:/out" \
  "ugekazna-backend:$VERSION" sh -c 'python /s/gen_secrets.py /out >/dev/null &&
    python /s/gen_selfsigned_tls.py --out /out --name ugk.selftest --days 90 \
      --cert-file tls_cert.pem --key-file tls_key.pem'
# Docker Desktop (Windows) konteynerda yaratilgan fayl huquqini (0600) host chmod'i o'zgartirmaydi:
# sirlar host tomonida qayta yoziladi, keyin faqat sinov uchun 0444 (uid 70/999/10001 o'qiy olsin).
mv "$WORK/secrets" "$WORK/secrets.gen"
mkdir "$WORK/secrets"
for f in "$WORK"/secrets.gen/*; do cat "$f" > "$WORK/secrets/$(basename "$f")"; done
rm -rf "$WORK/secrets.gen"
chmod 0444 "$WORK"/secrets/*
cat > "$WORK/selftest.env" <<EOF
UGK_VERSION=$VERSION
UGK_DOMAIN=ugk.selftest
UGK_BIND_ADDR=127.0.0.1
UGK_HTTPS_PORT=18443
UGK_HTTP_PORT=18080
UGK_WEB_SUBNET=172.31.252.0/24
UGK_PG_PROFILE=ci
UGK_DB_MEM=1g
UGK_DB_CPUS=1
UGK_SECRETS_DIR=$WORK/secrets
UGK_BACKUP_VOLUME=$VOLUME
UGK_BACKUP_INITIAL_FULL=no
SMTP_HOST=
SMTP_PORT=25
SMTP_FROM=ugekazna@selftest.local
SMTP_TO=
SMTP_USER=
EOF
docker volume create "$VOLUME" >/dev/null

# Izolyatsiya: sirlar $WORK ichida, repo hajmi sinov hajmi (prod sirlari/repo'ga tegmaydi).
CONFIG="$("${P[@]}" config | tr -d '\r')"
printf '%s\n' "$CONFIG" | grep -q "build.selftest.secrets" || die "sirlar papkasi $WORK/secrets emas"
printf '%s\n' "$CONFIG" | grep -q "name: $VOLUME\$" || die "repo hajmi $VOLUME emas"
! printf '%s\n' "$CONFIG" | grep -q "deploy.secrets" || die "prod sirlari ulangan"

step "1. prod stack (read_only, cap_drop, non-root, ci profili)"
"${P[@]}" up -d
for svc in db redis api worker caddy; do wait_healthy "$svc" 300; done
[ "$("${P[@]}" ps -a --format '{{.State}} {{.ExitCode}}' migrate | tr -d '\r')" = "exited 0" ] \
  || die "migrate 0 kodi bilan tugamadi"

step "2. bo'sh repo: restore_test.sh → 3, qoldiq yo'q, fail yozilgan"
set +e
scripts/restore_test.sh
code=$?
set -e
[ "$code" -eq 3 ] || die "bo'sh repo'da kutilgan kod 3, olingan $code"
[ -z "$("${R[@]}" ps -a -q | tr -d '\r')" ] || die "vaqtinchalik klaster konteynerlari qoldi"
STATUS="$("${P[@]}" run --rm -T --no-deps migrate python -m app.cli restore-test-status || true)"
case "$STATUS" in *'"result": "fail"'*) ;; *) die "bo'sh repo natijasi fail sifatida yozilmadi" ;; esac

step "3. sintetik ma'lumot va prod API smoke"
"${P[@]}" run --rm -T --no-deps migrate python -m app.cli create-admin \
  --username selftest_admin --full-name "Самопроверка"
"${P[@]}" run --rm -T --no-deps -e ENV=test worker python -m app.cli etl-run --source synthetic --mode full
TOKEN="$("${P[@]}" run --rm -T --no-deps -e ENV=test migrate python -m app.devtools seed-load --users 1 \
  | tr -d '\r' | tail -n 1 | sed -n 's/.*"token": *"\([^"]*\)".*/\1/p')"
[ -n "$TOKEN" ] || die "seed-load sessiya tokenini bermadi"
for i in 1 2; do
  http="$(http_code -H "Cookie: __Host-ugk_session=$TOKEN" https://ugk.selftest:18443/api/v1/meta/branches)"
  [ "$http" = 200 ] || die "/meta/branches ($i-chaqiruv) → $http"
done
[ "$(http_code https://ugk.selftest:18443/api/v1/healthz)" = 404 ] \
  || die "healthz tashqaridan ochiq"
[ "$(curl -s -o /dev/null -w '%{http_code}' --resolve ugk.selftest:18080:127.0.0.1 http://ugk.selftest:18080/)" = 308 ] \
  || die "HTTP → HTTPS yo'naltirish yo'q"
# prod-config stack'da yuklama foydalanuvchilari qolmasin (ops-check load_users_present)
"${P[@]}" run --rm -T --no-deps -e ENV=test migrate python -m app.devtools seed-load --purge

step "4. to'liq zaxira"
"${P[@]}" exec -T backup ugk-backup once full
[ -n "$("${P[@]}" exec -T backup ugk-backup latest | tr -d '\r')" ] || die "zaxira yorlig'i yo'q"

step "5. zaxiradan keyin yozuv + WAL arxivi"
"${P[@]}" run --rm -T --no-deps migrate python -m app.cli create-admin \
  --username after_backup --full-name "После резервной копии"
before="$(psql_prod 'SELECT archived_count FROM pg_stat_archiver')"
psql_prod 'SELECT pg_switch_wal()' >/dev/null
archived="$before"
for _ in $(seq 1 60); do
  archived="$(psql_prod 'SELECT archived_count FROM pg_stat_archiver')"
  if [ "$archived" -gt "$before" ]; then break; fi
  sleep 2
done
[ "$archived" -gt "$before" ] || die "WAL segmenti arxivlanmadi (archive-push)"

step "6. restore_test.sh → ok"
UGK_RESTORE_KEEP=1 scripts/restore_test.sh
STATUS="$("${P[@]}" run --rm -T --no-deps migrate python -m app.cli restore-test-status)" \
  || die "restore-test-status muammo ko'rsatdi"
case "$STATUS" in *'"result": "ok"'*) ;; *) die "ok natija yozilmadi: $STATUS" ;; esac

step "7. tiklangan nusxada zaxiradan keyingi yozuv bor (WAL replay)"
restored="$("${R[@]}" exec -T restore-db psql -U postgres -d ugekazna -tAc \
  "SELECT count(*) FROM core.users WHERE username = 'after_backup'" | tr -d '\r')"
[ "$restored" = 1 ] || die "zaxiradan keyingi yozuv tiklanmadi (count=$restored)"
"${R[@]}" down -v --remove-orphans >/dev/null

step "8. prod repo toza: tiklangan klaster timeline'i yo'q"
history="$("${P[@]}" exec -T backup sh -c \
  'find /var/lib/pgbackrest/archive -name "00000002.history*" | wc -l' | tr -d '\r ')"
[ "$history" = 0 ] || die "repo'da 00000002.history bor — tiklangan klaster WAL yuborgan"
"${P[@]}" exec -T backup pgbackrest --stanza=ugk check >/dev/null || die "prod WAL arxivi buzilgan"

step "9. monitor.sh"
scripts/ops/monitor.sh || die "monitor sog' stack'da muammo ko'rsatdi"
[ "$("${P[@]}" ps --format '{{.Health}}' redis | tr -d '\r')" = healthy ] || die "redis unhealthy"
"${P[@]}" stop backup >/dev/null
if scripts/ops/monitor.sh; then die "monitor to'xtatilgan backup'ni sezmadi"; fi
"${P[@]}" start backup >/dev/null

printf '\nSELFTEST: OK\n'
