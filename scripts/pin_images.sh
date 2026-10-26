#!/usr/bin/env bash
# Base image'larni hozirgi digest'iga qotiradi va deploy/images.lock.env ni qayta yozadi.
# Yangilash tartibi (docs/ops/install-upgrade.md, "Обновление базовых образов"):
#   scripts/pin_images.sh → git diff deploy/images.lock.env → make check scan backup-selftest → commit.
# Qayta ko'rish (2026-12-01 yoki CADDY_IMAGE yangilanganda): frontend/Dockerfile dagi `--replace golang.org/x/net=…`
#   pin yangi caddy'dagi x/net dan eski bo'lmasligi kerak (`go version -m` yoki SBOM) — kerak bo'lmasa olib tashlang.
# CPython, PostgreSQL, Redis manbadan yig'ilgan: Trivy ularning CVE'sini ko'rmaydi (pkg:generic SBOM'da
#   faqat inventar uchun, sbom_runtime.py). Ularning tuzatmalari faqat shu skriptni qayta ishlatish
#   (base re-pin) orqali keladi — takrorlash davri va upstream advisory kuzatuvi docs/ops da.
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGES=(
  "PYTHON_IMAGE=python:3.12-slim-bookworm"
  "NODE_IMAGE=node:22-alpine"
  "CADDY_IMAGE=caddy:2-alpine"
  "CADDY_BUILDER_IMAGE=caddy:builder-alpine"
  "POSTGRES_IMAGE=postgres:16-alpine"
  "REDIS_IMAGE=redis:7-alpine"
)
OUT=deploy/images.lock.env
TMP="$(mktemp)"
{
  echo "# Uchinchi tomon base image'lar digest bo'yicha qotirilgan (spec 2). Qo'lda tahrirlamang."
  echo "# Yangilash: scripts/pin_images.sh. Yaratilgan: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$TMP"
for entry in "${IMAGES[@]}"; do
  var="${entry%%=*}"
  ref="${entry#*=}"
  docker pull -q "$ref" >/dev/null
  digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$ref" \
            | sed -n 's/.*@\(sha256:[0-9a-f]\{64\}\)$/\1/p' | head -n 1)"
  if [ -z "$digest" ]; then
    echo "XATO: $ref uchun digest topilmadi" >&2
    exit 1
  fi
  echo "$var=$ref@$digest" >> "$TMP"
done
mv "$TMP" "$OUT"
cat "$OUT"
