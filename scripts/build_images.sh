#!/usr/bin/env bash
# Prod image'lari qotirilgan base image'lardan (deploy/images.lock.env):
#   ugekazna-backend, ugekazna-web, ugekazna-db, ugekazna-redis — hammasi :<VERSION>.
# Redis ham qayta teglanadi: `docker save/load` digest havolasini saqlamaydi (air-gapped o'rnatish).
# Korporativ CA hech qaysi yakuniy runtime image'ga tushmaydi (backend: RUNTIME_EXTRA_CA=false).
# Foydalanish: scripts/build_images.sh <VERSION>
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:?VERSION kerak, masalan 1.0.0}"
set -a
# shellcheck disable=SC1091
. deploy/images.lock.env
set +a
docker build -t "ugekazna-backend:$VERSION" --build-arg "PYTHON_IMAGE=$PYTHON_IMAGE" backend
docker build -t "ugekazna-web:$VERSION" --target web \
  --build-arg "NODE_IMAGE=$NODE_IMAGE" --build-arg "CADDY_IMAGE=$CADDY_IMAGE" --build-arg "CADDY_BUILDER_IMAGE=$CADDY_BUILDER_IMAGE" frontend
docker build -t "ugekazna-db:$VERSION" -f deploy/postgres/Dockerfile \
  --build-arg "POSTGRES_IMAGE=$POSTGRES_IMAGE" deploy
docker pull -q "$REDIS_IMAGE" >/dev/null
docker tag "$REDIS_IMAGE" "ugekazna-redis:$VERSION"
echo "Image'lar tayyor: ugekazna-{backend,web,db,redis}:$VERSION"
