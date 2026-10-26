#!/usr/bin/env bash
# DB image smoke-testi: read-only rootfs + ci profili bilan initdb, kengaytmalar, rollar,
# pgBackRest mavjudligi va initdb loglarida parol yo'qligi.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/../.."
IMAGE=ugekazna-db:smoke
NAME=ugk-db-smoke
docker build -q -f deploy/postgres/Dockerfile -t "$IMAGE" deploy >/dev/null
docker rm -f -v "$NAME" >/dev/null 2>&1 || true
trap 'docker rm -f -v "$NAME" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$NAME" --read-only --tmpfs /tmp --tmpfs /var/run/postgresql \
  -e UGK_PG_PROFILE=ci -e POSTGRES_DB=ugekazna -e POSTGRES_PASSWORD=smoke-superuser-pw \
  -e DB_MIGRATOR_PASSWORD=smoke-migrator-pw -e DB_APP_PASSWORD=smoke-app-pw -e DB_ETL_PASSWORD=smoke-etl-pw \
  "$IMAGE" >/dev/null
# initdb vaqtinchalik server bilan ishlaydi — "init process complete" dan keyingina tekshiramiz.
# (pipefail ostida `grep -q` ishlatilmaydi: erta chiqish SIGPIPE beradi va shart yolg'on bo'lib qoladi.)
for _ in $(seq 1 90); do
  if docker logs "$NAME" 2>&1 | grep "PostgreSQL init process complete" >/dev/null \
    && docker exec "$NAME" psql -U postgres -d ugekazna -tAc "SELECT 1" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
q() { docker exec "$NAME" psql -U postgres -d ugekazna -tAc "$1"; }
check() {
  if [ "$2" != "$3" ]; then echo "XATO: $1: kutilgan '$3', olingan '$2'" >&2; exit 1; fi
  echo "OK: $1 = $2"
}
check shared_preload_libraries "$(q 'SHOW shared_preload_libraries')" "pg_stat_statements,auto_explain"
check password_encryption "$(q 'SHOW password_encryption')" "scram-sha-256"
check archive_timeout "$(q 'SHOW archive_timeout')" "15min"
check shared_buffers "$(q 'SHOW shared_buffers')" "128MB"
check pg_stat_statements "$(q "SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'")" "1"
check ugk_roles "$(q "SELECT count(*) FROM pg_roles WHERE rolname IN ('ugk_app','ugk_etl','ugk_migrator')")" "3"
docker exec "$NAME" pgbackrest version
if docker logs "$NAME" 2>&1 | grep -e smoke-app-pw -e smoke-migrator-pw -e smoke-etl-pw >/dev/null; then
  echo "XATO: rol paroli konteyner logida" >&2
  exit 1
fi
echo "OK: loglarda parol yo'q"
