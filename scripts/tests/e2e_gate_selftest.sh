#!/usr/bin/env bash
# scripts/e2e_typecheck.sh sinovi: toza e2e — 0, ataylab buzilgan spec (tirnoq xatosi) — noldan farqli kod.
set -euo pipefail
cd "$(dirname "$0")/../.."
W=build/e2e-gate-selftest
trap 'rm -rf "$W"' EXIT
rm -rf "$W"; mkdir -p "$W"
cp -r frontend/e2e "$W/e2e"; rm -rf "$W/e2e/node_modules"

scripts/e2e_typecheck.sh "$W/e2e" >/dev/null
echo "OK: toza e2e o'tdi"

printf "const bad = 'oqim bog'liq emas';\n" > "$W/e2e/specs/zz-broken.spec.ts"
rc=0
scripts/e2e_typecheck.sh "$W/e2e" >/dev/null 2>&1 || rc=$?
if [ "$rc" -eq 0 ]; then
  echo "XATO: buzilgan spec darvozadan o'tdi (no-op darvoza)" >&2
  exit 1
fi
echo "OK: buzilgan spec to'xtatildi (kod $rc)"
