#!/usr/bin/env bash
# Reliz paketi (docs/ops/install-upgrade.md): image'lar (docker save), SBOM, deploy/, scripts/,
# docs/security, docs/ops, Makefile, deploy/release.env, COMMIT, SHA256SUMS.
# Image'lar ishchi daraxtdan emas, `git archive HEAD` eksportidan quriladi va skanerlanadi:
# COMMIT aynan qurilgan narsaga teng (kuzatilmayotgan/ignor qilingan fayllar image'ga tushmaydi).
# Natija: build/release/ugekazna-<VERSION>.tar.gz. Foydalanish: scripts/release.sh <VERSION>
# Eslatma: docs/ops yaratilguncha (14-vazifa) `make release` ataylab xato bilan tugaydi.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:?VERSION kerak, masalan 1.0.0}"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "XATO: ishchi daraxt toza emas — reliz faqat commit qilingan holatdan" >&2
  exit 1
fi
SRC="build/src-$VERSION"
PATHS=(deploy scripts docs/security docs/ops Makefile)
rm -rf "$SRC"
mkdir -p "$SRC"
git archive HEAD | tar -x -C "$SRC"
for path in "${PATHS[@]}"; do
  if [ ! -e "$SRC/$path" ]; then
    echo "XATO: $path HEAD'da yo'q — paket to'liq emas" >&2
    exit 1
  fi
done
# O'z-o'zini tekshirish: eksport HEAD'dagi barcha kuzatiladigan fayllarni (va faqat ularni) o'z ichiga oladi.
tracked="$(git ls-tree -r --name-only HEAD | wc -l)"
exported="$(find "$SRC" \( -type f -o -type l \) | wc -l)"
if [ "$tracked" -ne "$exported" ]; then
  echo "XATO: eksport HEAD'ga mos emas (kuzatiladigan $tracked, eksport $exported)" >&2
  exit 1
fi
# Trivy bazasi qayta yuklanmasligi uchun kesh eksportga ko'chiriladi va keyin qaytariladi.
mkdir -p "$SRC/build" build/.trivy-cache
cp -r build/.trivy-cache "$SRC/build/.trivy-cache"
(cd "$SRC" && scripts/scan.sh "$VERSION")
rm -rf build/.trivy-cache
cp -r "$SRC/build/.trivy-cache" build/.trivy-cache
OUT="build/release/ugekazna-$VERSION"
rm -rf "$OUT"
mkdir -p "$OUT/images" "$OUT/sbom"
docker save -o "$OUT/images/ugekazna-images-$VERSION.tar" \
  "ugekazna-backend:$VERSION" "ugekazna-web:$VERSION" "ugekazna-db:$VERSION" "ugekazna-redis:$VERSION"
cp "$SRC"/build/sbom/*.cdx.json "$OUT/sbom/"
tar -C "$SRC" -c "${PATHS[@]}" | tar -x -C "$OUT"
printf 'UGK_VERSION=%s\n' "$VERSION" > "$OUT/deploy/release.env"
git rev-parse HEAD > "$OUT/COMMIT"
(cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -C build/release -czf "build/release/ugekazna-$VERSION.tar.gz" "ugekazna-$VERSION"
rm -rf "$SRC"
echo "Reliz: build/release/ugekazna-$VERSION.tar.gz"
