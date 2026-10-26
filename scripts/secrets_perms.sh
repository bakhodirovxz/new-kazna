#!/usr/bin/env bash
# Prod sirlari huquqlari (spec 2): egasi root, guruh — konteynerlardagi 10001 guruhi, fayllar 0440,
# papka 0750. Docker userns-remap yoqilgan bo'lsa konteyner gid 10001 host'da (dockremap subgid bazasi
# + 10001) ga mos keladi. Foydalanish (root): scripts/secrets_perms.sh /opt/ugekazna/shared/secrets
set -euo pipefail
DIR="${1:?sirlar papkasi kerak}"
if [ "$(id -u)" -ne 0 ]; then
  echo "root sifatida ishga tushiring" >&2
  exit 1
fi
GID=10001
# docker info yiqilsa — fail-closed (aks holda 10001 host guruhiga berib yuborilishi mumkin).
OPTS="$(docker info --format '{{json .SecurityOptions}}')" || { echo "docker info yiqildi" >&2; exit 1; }
if printf '%s' "$OPTS" | grep 'name=userns' >/dev/null; then
  BASE="$(awk -F: '$1 == "dockremap" { print $2; exit }' /etc/subgid)"
  if [ -z "$BASE" ]; then
    echo "/etc/subgid da dockremap yozuvi yo'q" >&2
    exit 1
  fi
  GID=$((BASE + 10001))
fi
chown root:"$GID" "$DIR"
chmod 0750 "$DIR"
if [ -n "$(find "$DIR" -maxdepth 1 -type l -print -quit)" ]; then
  echo "symlink sirlar rad etildi (haqiqiy fayl kerak): $DIR" >&2
  exit 1
fi
find "$DIR" -maxdepth 1 -type f -exec chown root:"$GID" {} + -exec chmod 0440 {} +
echo "OK: $DIR → root:$GID (fayllar 0440, papka 0750)"
