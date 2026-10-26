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
mkdir -p build/images build/sbom build/.trivy-cache
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
echo "== SBOM: frontend (npm, prod bog'liqliklar)"
"${TRIVY[@]}" fs --format cyclonedx --output /build/sbom/frontend-npm.cdx.json --no-progress \
  /src/frontend/package-lock.json
docker compose -f deploy/compose.test.yml run --rm -T --no-deps test \
  sh -c 'python /repo/scripts/check_sbom.py /repo/build/sbom/*.cdx.json'
if [ "$status" -ne 0 ]; then
  echo "make scan: Trivy HIGH/CRITICAL zaiflik topdi (yuqoridagi jadvallar)" >&2
fi
exit "$status"
