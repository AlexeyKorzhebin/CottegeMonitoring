#!/usr/bin/env bash
# Copy renewed Let's Encrypt cert into mosquitto. LogicMachine (old OpenSSL)
# fails TLS handshake on the new 3-cert YR2 chain — serve a 2-cert chain instead.
#
# Install on elion:
#   install -o root -g root -m 755 server/scripts/10-mosquitto-cert-hook.sh \
#     /etc/letsencrypt/renewal-hooks/deploy/10-mosquitto.sh
set -euo pipefail

LIVE=/etc/letsencrypt/live/elion.black-castle.ru
ARCH=/etc/letsencrypt/archive/elion.black-castle.ru
DST=/etc/mosquitto/certs
MIN_DAYS="${MIN_DAYS:-14}"
MIN_SECS=$((MIN_DAYS * 86400))
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

log() { logger -t mosquitto-cert "$*"; }

pick_privkey_for_fullchain() {
  local full="$1"
  local n
  n=$(basename "$full" | sed -n 's/fullchain\([0-9]*\)\.pem/\1/p')
  if [[ -n "$n" && -r "$ARCH/privkey${n}.pem" ]]; then
    echo "$ARCH/privkey${n}.pem"
    return 0
  fi
  if [[ -r "$LIVE/privkey.pem" ]]; then
    echo "$LIVE/privkey.pem"
    return 0
  fi
  return 1
}

write_short_chain() {
  local src_full="$1"
  awk '/BEGIN CERT/{c++} c<=2' "$src_full" >"$TMP"
  local blocks
  blocks=$(grep -c "BEGIN CERTIFICATE" "$TMP" || echo 0)
  if [[ "$blocks" -ne 2 ]]; then
    log "FAIL: cannot build 2-block chain from $src_full (got $blocks)"
    return 1
  fi
  if ! openssl x509 -in "$TMP" -noout -checkend "$MIN_SECS" >/dev/null 2>&1; then
    log "WARN: short chain from $src_full expires within ${MIN_DAYS}d"
  fi
  echo "$TMP"
  return 0
}

src_full="$LIVE/fullchain.pem"
src_key="$(pick_privkey_for_fullchain "$src_full")"
blocks=$(grep -c "BEGIN CERTIFICATE" "$src_full" || echo 0)

if [[ "$blocks" -eq 2 ]]; then
  : # live already LM-compatible
elif [[ "$blocks" -gt 2 ]]; then
  candidate=""
  for f in $(ls -1t "$ARCH"/fullchain*.pem 2>/dev/null); do
    b=$(grep -c "BEGIN CERTIFICATE" "$f" || echo 0)
    if [[ "$b" -eq 2 ]] && openssl x509 -in "$f" -noout -checkend "$MIN_SECS" >/dev/null 2>&1; then
      candidate="$f"
      break
    fi
  done
  if [[ -n "$candidate" ]]; then
    src_full="$candidate"
    src_key="$(pick_privkey_for_fullchain "$candidate")"
    log "LM compat: using archive short chain $candidate (live has $blocks blocks)"
  else
  # No valid legacy R12 archive — trim newest fullchain to leaf + first intermediate (YR2).
    newest="$(ls -1t "$ARCH"/fullchain*.pem 2>/dev/null | head -1)"
    if [[ -z "$newest" ]]; then
      newest="$LIVE/fullchain.pem"
    fi
    trimmed="$(write_short_chain "$newest")" || exit 1
    src_full="$trimmed"
    src_key="$(pick_privkey_for_fullchain "$newest")"
    log "LM compat: trimmed $newest to 2 PEM blocks (live has $blocks blocks)"
  fi
else
  log "FAIL: unexpected PEM block count in $src_full: $blocks"
  exit 1
fi

install -o root -g mosquitto -m 640 "$src_full" "$DST/fullchain.pem"
install -o root -g mosquitto -m 640 "$src_key" "$DST/privkey.pem"
systemctl reload mosquitto 2>/dev/null || systemctl restart mosquitto
log "mosquitto certs updated from $(basename "$src_full")"
