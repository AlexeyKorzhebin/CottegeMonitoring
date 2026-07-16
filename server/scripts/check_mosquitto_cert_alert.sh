#!/usr/bin/env bash
# Run mosquitto/LM cert check; on failure notify Telegram (+ syslog).
# Uses /etc/cottage-monitoring/telegram.env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).
set -euo pipefail

CHECK="${CHECK_BIN:-/usr/local/sbin/check_mosquitto_cert.sh}"
TELEGRAM_ENV="${TELEGRAM_ENV:-/etc/cottage-monitoring/telegram.env}"
LOG="${LOG:-/var/log/cottage-monitoring/cert-check.log}"
HOSTNAME_SHORT="$(hostname -s 2>/dev/null || hostname)"

mkdir -p "$(dirname "$LOG")"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

set +e
out="$("$CHECK" 2>&1)"
rc=$?
set -e

{
  echo "==== $ts rc=$rc ===="
  echo "$out"
} >>"$LOG"

if [[ "$rc" -eq 0 ]]; then
  exit 0
fi

logger -t mosquitto-cert "LM cert check FAILED (rc=$rc) on $HOSTNAME_SHORT"
msg="🚨 CottageMonitoring TLS/mosquitto cert check FAILED on ${HOSTNAME_SHORT}
rc=${rc}
${out}
(auto-check; if LM goes offline after renew — short-chain / expiry)"

if [[ -r "$TELEGRAM_ENV" ]]; then
  # shellcheck disable=SC1090
  set -a
  # only export known keys
  eval "$(grep -E '^(TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|TELEGRAM_OWNER_ID)=' "$TELEGRAM_ENV" | sed 's/^/export /')"
  set +a
  chat="${TELEGRAM_CHAT_ID:-${TELEGRAM_OWNER_ID:-}}"
  if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "$chat" ]]; then
    curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${chat}" \
      --data-urlencode "text=${msg}" \
      -d "disable_web_page_preview=true" >/dev/null \
      || logger -t mosquitto-cert "Telegram notify failed"
  else
    logger -t mosquitto-cert "telegram.env incomplete — no notify"
  fi
else
  logger -t mosquitto-cert "no $TELEGRAM_ENV — syslog only"
fi

exit "$rc"
