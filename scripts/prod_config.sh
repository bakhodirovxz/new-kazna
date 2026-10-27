#!/usr/bin/env bash
# compose.prod.yml sintaksisi va interpolatsiyasini tekshiradi (docker compose config -q).
# `config` sir fayllari mavjudligini talab qiladi — mazmuni tekshirilmaydi, shuning uchun bo'sh fayllar.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR=build/prod-config/secrets
rm -rf build/prod-config
mkdir -p "$DIR"
for name in db_superuser_password db_migrator_password db_app_password db_etl_password redis_password \
            master_kek blind_index_key session_pepper smtp_password pgbackrest_cipher_pass \
            tls_cert.pem tls_key.pem onec_ca_bundle.pem; do
  : > "$DIR/$name"
done
# UGK_SECRETS_DIR compose fayli papkasiga (deploy/) nisbatan.
UGK_VERSION=config-check UGK_SECRETS_DIR=../build/prod-config/secrets \
  docker compose -f deploy/compose.prod.yml --env-file deploy/prod.env.example config -q
echo "prod-config: OK"
