#!/usr/bin/env bash
# Reliz paketi (docs/ops/install-upgrade.md): image'lar (docker save), SBOM, deploy/, scripts/,
# docs/security, docs/ops, Makefile, deploy/release.env, COMMIT, SHA256SUMS.
# Natija: build/release/ugekazna-<VERSION>.tar.gz. Foydalanish: scripts/release.sh <VERSION>
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:?VERSION kerak, masalan 1.0.0}"
# Paket `git archive HEAD` dan olinadi: kuzatilmayotgan fayllar unga tushmaydi, faqat o'zgargan tracked fayllar xavfli.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "XATO: ishchi daraxt toza emas — reliz faqat commit qilingan holatdan" >&2
  exit 1
fi
scripts/scan.sh "$VERSION"
OUT="build/release/ugekazna-$VERSION"
rm -rf "$OUT"
mkdir -p "$OUT/images" "$OUT/sbom"
docker save -o "$OUT/images/ugekazna-images-$VERSION.tar" \
  "ugekazna-backend:$VERSION" "ugekazna-web:$VERSION" "ugekazna-db:$VERSION" "ugekazna-redis:$VERSION"
cp build/sbom/*.cdx.json "$OUT/sbom/"
PATHS=()
for path in deploy scripts docs/security docs/ops Makefile; do
  if git cat-file -e "HEAD:$path" 2>/dev/null; then
    PATHS+=("$path")
  else
    echo "OGOHLANTIRISH: $path HEAD'da yo'q, paketga kirmaydi" >&2
  fi
done
git archive --format=tar HEAD "${PATHS[@]}" | tar -x -C "$OUT"
printf 'UGK_VERSION=%s\n' "$VERSION" > "$OUT/deploy/release.env"
git rev-parse HEAD > "$OUT/COMMIT"
(cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -C build/release -czf "build/release/ugekazna-$VERSION.tar.gz" "ugekazna-$VERSION"
echo "Reliz: build/release/ugekazna-$VERSION.tar.gz"
