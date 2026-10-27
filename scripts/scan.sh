#!/usr/bin/env bash
# make scan (spec 10): prod image'larini qotirilgan base'lardan quradi, Trivy (HIGH/CRITICAL,
# tuzatish mavjud → xato) va CycloneDX SBOM (build/sbom/). Foydalanish: scripts/scan.sh [VERSION]
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-$(git describe --tags --always --dirty)}"
UGK_UID="$(id -u)"
UGK_GID="$(id -g)"
export UGK_UID UGK_GID
# Git Bash (Windows) /build/... argumentlarini C:/Program Files/Git/... ga aylantirmasin.
export MSYS_NO_PATHCONV=1
scripts/build_images.sh "$VERSION"
set -a
# shellcheck disable=SC1091
. deploy/images.lock.env
set +a
# Image env'idan o'zgaruvchi qiymati (bo'sh bo'lsa — sbom_runtime.py xato beradi).
image_env() { docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$1" | sed -n "s/^$2=//p"; }
# Runtime komponentlari SBOM'ga pkg:generic sifatida (Trivy manbadan yig'ilgan CPython/PG/Redis/Caddy'ni ko'rmaydi).
add_runtime() { # <image nomi> <komponent> <env o'zgaruvchisi>
  local ver
  ver="$(image_env "$1:$VERSION" "$3")"
  docker run --rm --network none -u "$UGK_UID:$UGK_GID" -v "$PWD/build/sbom:/sbom" \
    -v "$PWD/scripts/sbom_runtime.py:/sbom_runtime.py:ro" "$PYTHON_IMAGE" \
    python /sbom_runtime.py "/sbom/$1.cdx.json" "$2=${ver#v}"
}
mkdir -p build/images build/sbom build/.trivy-cache
# Korporativ CA runtime image'larida ishonchli bo'lmasligi shart (faqat build vaqtida): regressiya himoyasi.
ca_file=backend/certs/organization-ca-3.crt
if [ -f "$ca_file" ]; then
  ca_line="$(sed -n 2p "$ca_file")"
  for name in ugekazna-backend ugekazna-web; do
    hits="$(docker run --rm --entrypoint grep "$name:$VERSION" -cF "$ca_line" /etc/ssl/certs/ca-certificates.crt || true)"
    if [ "$hits" != 0 ]; then
      echo "XATO: korporativ CA $name image'iga tushib qolgan" >&2
      exit 1
    fi
  done
fi
TRIVY=(docker compose -f deploy/compose.tools.yml run --rm -T trivy)
status=0
for name in ugekazna-backend ugekazna-web ugekazna-db ugekazna-redis; do
  docker save -o "build/images/$name.tar" "$name:$VERSION"
  echo "== trivy $name:$VERSION"
  if ! "${TRIVY[@]}" image --input "/build/images/$name.tar" --severity HIGH,CRITICAL \
       --ignore-unfixed --exit-code 1 --ignorefile /src/.trivyignore --no-progress; then
    status=1
  fi
  "${TRIVY[@]}" image --input "/build/images/$name.tar" --format cyclonedx \
    --output "/build/sbom/$name.cdx.json" --no-progress
done
add_runtime ugekazna-backend python PYTHON_VERSION
add_runtime ugekazna-db postgresql PG_VERSION
add_runtime ugekazna-redis redis REDIS_VERSION
add_runtime ugekazna-web caddy CADDY_VERSION
echo "== SBOM: frontend (npm, prod bog'liqliklar)"
"${TRIVY[@]}" fs --format cyclonedx --output /build/sbom/frontend-npm.cdx.json --no-progress \
  /src/frontend/package-lock.json
docker compose -f deploy/compose.test.yml run --rm -T --no-deps test \
  sh -c 'python /repo/scripts/check_sbom.py /repo/build/sbom/*.cdx.json'
if [ "$status" -ne 0 ]; then
  echo "make scan: Trivy HIGH/CRITICAL zaiflik topdi (yuqoridagi jadvallar)" >&2
fi
exit "$status"
