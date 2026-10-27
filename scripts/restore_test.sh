#!/usr/bin/env bash
# Oylik tiklash testi (spec 11; TZ 9: "восстановление проверяется ежемесячно с записью результата";
# TZ 10, qabul mezoni 6). Oxirgi zaxirani alohida compose loyihasidagi vaqtinchalik klasterga
# tiklaydi (WAL oxirigacha, arxivlash O'CHIQ, repo faqat o'qish) va tekshiradi: alembic current =
# head, audit-verify ok, asosiy jadvallar qator soni, umumiy vaqt ≤ RTO (7200 s).
# Natija: $UGK_LOG_DIR/restore-test-<UTC>.log va prod core.settings `last_restore_test` (CLI orqali).
#
# Muhit:
#   UGK_ENV_FILES     vergul bilan ajratilgan env fayllar (standart: deploy/prod.env,deploy/release.env)
#   UGK_PROJECT       prod compose loyihasi (standart: ugekazna)
#   UGK_LOG_DIR       log papkasi (standart: build/restore-test; systemd'da /var/log/ugekazna)
#   UGK_RESTORE_KEEP  1 — vaqtinchalik klasterni tahlil uchun qoldirish (keyin: ... -restore down -v)
# Chiqish kodi: 0 — ok, 1 — tekshiruv xatosi, 3 — repo'da zaxira yo'q.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
DEPLOY="$ROOT/deploy"
: "${UGK_ENV_FILES:=$DEPLOY/prod.env,$DEPLOY/release.env}"
: "${UGK_PROJECT:=ugekazna}"
: "${UGK_LOG_DIR:=$ROOT/build/restore-test}"
: "${UGK_RESTORE_KEEP:=0}"
ENV_ARGS=()
IFS=',' read -r -a ENV_FILES <<< "$UGK_ENV_FILES"
for f in "${ENV_FILES[@]}"; do ENV_ARGS+=(--env-file "$f"); done
PROD=(docker compose -p "$UGK_PROJECT" -f "$DEPLOY/compose.prod.yml" "${ENV_ARGS[@]}")
RESTORE=(docker compose -p "$UGK_PROJECT-restore" -f "$DEPLOY/compose.restore.yml" "${ENV_ARGS[@]}")

mkdir -p "$UGK_LOG_DIR"
LOG="$UGK_LOG_DIR/restore-test-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG") 2>&1

START=$(date +%s)
RESULT=fail
BACKUP_LABEL=none
DETAILS="kutilmagan xato — log: $LOG"

psql_restore() { "${RESTORE[@]}" exec -T restore-db psql -U postgres -d ugekazna -tAc "$1" | tr -d '\r'; }

finish() {
  local code=$?
  local duration=$(( $(date +%s) - START ))
  if [ "$UGK_RESTORE_KEEP" != 1 ]; then
    # Vaqtinchalik nusxa prod ma'lumotining ochiq (shifrsiz) nusxasi: o'chmasa — ko'rinadigan xato (kod 1).
    if ! "${RESTORE[@]}" down -v --remove-orphans >/dev/null 2>&1; then
      echo "XATO: vaqtinchalik klaster o'chirilmadi — qo'lda o'chiring (docs/ops/backup-restore.md, 4-bo'lim)" >&2
      DETAILS="vaqtinchalik klaster o'chirilmadi"
      RESULT=fail
      [ "$code" -ne 0 ] || code=1
    fi
  fi
  # CLI faqat pgBackRest yorlig'i yoki `none` qabul qiladi — boshqa qiymat yozuvni yo'qotmasin.
  [[ $BACKUP_LABEL =~ ^[0-9]{8}-[0-9]{6}F(_[0-9]{8}-[0-9]{6}[DI])?$ ]] || BACKUP_LABEL=none
  echo "== natija: $RESULT, ${duration} s, zaxira: $BACKUP_LABEL (kod $code)"
  if ! "${PROD[@]}" run --rm -T --no-deps migrate python -m app.cli restore-test-record \
      --result "$RESULT" --duration-seconds "$duration" --backup "$BACKUP_LABEL" --details "$DETAILS"; then
    echo "XATO: natijani prod bazaga yozib bo'lmadi" >&2
    [ "$code" -ne 0 ] || code=1
  fi
  exit "$code"
}
trap finish EXIT
fail() { DETAILS="$2"; echo "XATO: $2" >&2; exit "$1"; }

echo "== 1/6 oxirgi zaxira"
BACKUP_LABEL="$("${PROD[@]}" exec -T backup ugk-backup latest | tr -d '\r')" \
  || { BACKUP_LABEL=none; fail 1 "ugk-backup latest xatosi"; }
if [ -z "$BACKUP_LABEL" ]; then
  BACKUP_LABEL=none
  fail 3 "repo'da zaxira yo'q"
fi
echo "zaxira: $BACKUP_LABEL"

echo "== 2/6 tiklash: WAL oxirigacha, arxivlash o'chiq, repo faqat o'qish"
"${RESTORE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${RESTORE[@]}" run --rm -T restore-db ugk-restore "--set=$BACKUP_LABEL" || fail 1 "pgbackrest restore xatosi"

echo "== 3/6 PostgreSQL: WAL replay va promote"
"${RESTORE[@]}" up -d restore-db || fail 1 "restore-db ishga tushmadi"
promoted=no
for _ in $(seq 1 720); do
  if [ "$(psql_restore 'SELECT pg_is_in_recovery()' 2>/dev/null || true)" = f ]; then
    promoted=yes
    break
  fi
  if [ "$("${RESTORE[@]}" ps -a --format '{{.State}}' restore-db | tr -d '\r')" = exited ]; then
    "${RESTORE[@]}" logs --tail=40 restore-db || true
    fail 1 "restore-db tiklash paytida to'xtadi"
  fi
  sleep 10
done
[ "$promoted" = yes ] || fail 1 "klaster 2 soat ichida recovery'dan chiqmadi"
[ "$(psql_restore 'SHOW archive_mode')" = off ] || fail 1 "tiklangan klasterda archive_mode off emas"

echo "== 4/6 sxema versiyasi"
CURRENT="$("${RESTORE[@]}" run --rm -T check alembic current 2>&1)" || fail 1 "alembic current xatosi"
echo "$CURRENT"
case "$CURRENT" in
  *"(head)"*) ;;
  *) fail 1 "sxema head emas" ;;
esac

echo "== 5/6 audit zanjiri"
"${RESTORE[@]}" run --rm -T check python -m app.cli audit-verify || fail 1 "audit-verify: zanjir buzilgan"

echo "== 6/6 qatorlar soni"
COUNTS="$(psql_restore "SELECT 'core.users=' || count(*) FROM core.users
  UNION ALL SELECT 'core.audit_log=' || count(*) FROM core.audit_log
  UNION ALL SELECT 'core.etl_run=' || count(*) FROM core.etl_run
  UNION ALL SELECT 'dwh.fact_cashflow=' || count(*) FROM dwh.fact_cashflow
  UNION ALL SELECT 'mart.agg_cash_month=' || count(*) FROM mart.agg_cash_month")" \
  || fail 1 "qatorlar sonini o'qib bo'lmadi"
echo "$COUNTS"
DETAILS="$(printf '%s' "$COUNTS" | tr '\n' ';')"
USERS="$(printf '%s\n' "$COUNTS" | sed -n 's/^core\.users=//p')"
[ "${USERS:-0}" -gt 0 ] || fail 1 "core.users bo'sh — $DETAILS"
if [ $(( $(date +%s) - START )) -gt 7200 ]; then
  fail 1 "RTO (7200 s) oshdi — $DETAILS"
fi
RESULT=ok
