#!/usr/bin/env bash
# .githooks/pre-commit sinovi: staged sir bo'lsa hook noldan farqli kod qaytaradi, toza o'zgarishda — 0.
set -euo pipefail
cd "$(dirname "$0")/../.."
if ! git diff --cached --quiet; then
  echo "Avval staged o'zgarishlarni commit qiling yoki unstage qiling" >&2
  exit 2
fi
F=build/hook-selftest/leak.txt
mkdir -p "$(dirname "$F")"
cleanup() { git reset -q -- "$F" 2>/dev/null || true; rm -rf build/hook-selftest; }
trap cleanup EXIT

printf 'GITHUB_TOKEN = "ghp_%s"\n' "$(od -An -N18 -tx1 /dev/urandom | tr -d ' \n')" > "$F"
git add -f "$F"
rc=0
.githooks/pre-commit || rc=$?
if [ "$rc" -ne 1 ]; then
  echo "XATO: hook chiqish kodi $rc (kutilgan: 1 — gitleaks sirni topdi)" >&2
  exit 1
fi
echo "OK: hook sirli commit'ni to'xtatdi"

git reset -q -- "$F"
printf 'oddiy matn\n' > "$F"
git add -f "$F"
.githooks/pre-commit
echo "OK: toza staged o'zgarish o'tdi"
