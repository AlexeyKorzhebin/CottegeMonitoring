#!/usr/bin/env bash
# Verify mosquitto TLS cert is LM-compatible (2 PEM blocks) and not expired.
# Run on elion: sudo ./check_mosquitto_cert.sh
set -euo pipefail

CERT="${1:-/etc/mosquitto/certs/fullchain.pem}"
MIN_DAYS="${MIN_DAYS:-14}"

if [[ ! -r "$CERT" ]]; then
  echo "FAIL: cannot read $CERT" >&2
  exit 2
fi

blocks=$(grep -c "BEGIN CERTIFICATE" "$CERT" || echo 0)
issuer=$(openssl x509 -in "$CERT" -noout -issuer 2>/dev/null | sed 's/^issuer=//')
end=$(openssl x509 -in "$CERT" -noout -enddate 2>/dev/null | cut -d= -f2)

echo "cert=$CERT"
echo "blocks=$blocks"
echo "issuer=$issuer"
echo "notAfter=$end"

ok=0
if [[ "$blocks" -ne 2 ]]; then
  echo "FAIL: need exactly 2 PEM blocks for LogicMachine (got $blocks)" >&2
  ok=1
fi

secs=$((MIN_DAYS * 86400))
if ! openssl x509 -in "$CERT" -noout -checkend "$secs" >/dev/null 2>&1; then
  echo "FAIL: certificate expires within ${MIN_DAYS} days" >&2
  ok=1
fi

if [[ "$ok" -eq 0 ]]; then
  echo "OK: LM-compatible short chain, valid >${MIN_DAYS}d"
  exit 0
fi
exit 1
