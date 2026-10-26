#!/usr/bin/env bash
# Review Focus 4: gitleaks istisnosi haqiqiy sirni yashirmasligi kerak.
# 1) ochiq test qiymatlari (TEST_KEYS, E2E TOTP siri) — topilmaydi;
# 2) xuddi shu faylga qo'shilgan haqiqiy ko'rinishdagi GitHub token — topilishi SHART.
set -euo pipefail
cd "$(dirname "$0")/../.."
DIR=build/gitleaks-selftest
rm -rf "$DIR"
mkdir -p "$DIR"
trap 'rm -rf "$DIR"' EXIT
RUN=(docker compose -f deploy/compose.tools.yml run --rm -T gitleaks-selftest)

cat > "$DIR/allowed.py" <<'PYEOF'
MASTER_KEK = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
SESSION_PEPPER = "QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8="
E2E_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
PYEOF
"${RUN[@]}"
echo "OK: ochiq test qiymatlari istisno qilingan"

# Token ish vaqtida yasaladi — repo'da haqiqiy ko'rinishdagi token saqlanmaydi.
printf 'GITHUB_TOKEN = "ghp_%s"\n' "$(od -An -N18 -tx1 /dev/urandom | tr -d ' \n')" >> "$DIR/allowed.py"
rc=0
"${RUN[@]}" || rc=$?
if [ "$rc" -ne 1 ]; then
  echo "XATO: gitleaks chiqish kodi $rc (kutilgan: 1 — token topildi)" >&2
  exit 1
fi
echo "OK: haqiqiy token topildi"
