#!/usr/bin/env bash
# Prod monitoring (docs/ops/monitoring.md). systemd timer har 15 daqiqada ishga tushiradi.
#  1) har uzoq ishlaydigan servis ishlayapti va unhealthy emas;
#  2) ops-check worker ichida (DB holati, tiklash testi, kalitlar yoshi, soat farqi, TLS muddati),
#     muammo bo'lsa SMTP orqali bitta xabar (worker'dagi SMTP_* sozlamalari).
# Muhit: UGK_PROJECT (ugekazna), UGK_ENV_FILES (deploy/prod.env,deploy/release.env).
# Chiqish kodi: 0 — hammasi joyida, 1 — muammo (journald: SyslogIdentifier=ugekazna-monitor).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && (pwd -W 2>/dev/null || pwd))"
DEPLOY="$ROOT/deploy"
: "${UGK_ENV_FILES:=$DEPLOY/prod.env,$DEPLOY/release.env}"
: "${UGK_PROJECT:=ugekazna}"
ENV_ARGS=()
IFS=',' read -r -a ENV_FILES <<< "$UGK_ENV_FILES"
for f in "${ENV_FILES[@]}"; do ENV_ARGS+=(--env-file "$f"); done
P=(docker compose -p "$UGK_PROJECT" -f "$DEPLOY/compose.prod.yml" "${ENV_ARGS[@]}")
SERVICES=(db redis api worker caddy backup)

extra=()
for svc in "${SERVICES[@]}"; do
  state="$("${P[@]}" ps --format '{{.State}} {{.Health}}' "$svc" 2>/dev/null | tr -d '\r' | sed -n 1p)"
  case "$state" in
    "running healthy"|"running starting") ;;
    *) extra+=(--extra "$svc: ${state:-не запущен}") ;;
  esac
done

if "${P[@]}" ps --format '{{.State}}' worker 2>/dev/null | grep running >/dev/null; then
  if "${P[@]}" exec -T worker python -m app.cli ops-check --notify \
       --tls-cert /run/secrets/tls_cert "${extra[@]}"; then
    exit 0
  fi
  exit 1
fi
logger -t ugekazna-monitor -p user.err "worker ishlamayapti: ${extra[*]}" 2>/dev/null || true
echo "worker ishlamayapti — ops-check bajarilmadi: ${extra[*]}" >&2
exit 1
