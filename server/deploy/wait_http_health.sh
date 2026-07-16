#!/usr/bin/env bash
# Wait until CottageMonitoring /health responds (used by systemd ExecStartPost).
set -euo pipefail

URL="${1:?health URL required}"
ATTEMPTS="${2:-30}"

for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
  if /usr/bin/curl --fail --silent --show-error --max-time 2 "$URL" >/dev/null; then
    echo "healthy: $URL (attempt $attempt/$ATTEMPTS)"
    exit 0
  fi
  /usr/bin/sleep 1
done

echo "health endpoint did not become ready: $URL" >&2
exit 1
