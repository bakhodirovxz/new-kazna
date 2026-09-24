#!/bin/sh
# Ilova uchun uchta DB roli (spec 3.4). Parollar Docker secrets'dan yoki (test) env'dan.
set -eu

secret() {
  file="/run/secrets/$1"
  if [ -r "$file" ]; then cat "$file"; else printenv "$2" || true; fi
}

MIGRATOR_PW="$(secret db_migrator_password DB_MIGRATOR_PASSWORD)"
APP_PW="$(secret db_app_password DB_APP_PASSWORD)"
ETL_PW="$(secret db_etl_password DB_ETL_PASSWORD)"

for v in "$MIGRATOR_PW" "$APP_PW" "$ETL_PW"; do
  if [ -z "$v" ]; then
    echo "01-roles.sh: DB rollari paroli topilmadi" >&2
    exit 1
  fi
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v migrator_pw="$MIGRATOR_PW" -v app_pw="$APP_PW" -v etl_pw="$ETL_PW" \
  -v dbname="$POSTGRES_DB" <<'SQL'
CREATE ROLE ugk_migrator LOGIN PASSWORD :'migrator_pw';
CREATE ROLE ugk_app LOGIN NOBYPASSRLS PASSWORD :'app_pw';
CREATE ROLE ugk_etl LOGIN NOBYPASSRLS PASSWORD :'etl_pw';
ALTER DATABASE :"dbname" OWNER TO ugk_migrator;
REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dbname" TO ugk_migrator, ugk_app, ugk_etl;
ALTER SCHEMA public OWNER TO ugk_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL
