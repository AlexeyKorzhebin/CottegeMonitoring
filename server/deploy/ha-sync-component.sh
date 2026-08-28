#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# script lives in server/deploy → repo root is ../..
tar -C "$ROOT/ha/custom_components" -czf - cottage_monitoring \
  | ssh elion 'sudo mkdir -p /var/lib/homeassistant/custom_components \
    && sudo tar -C /var/lib/homeassistant/custom_components -xzf - \
    && sudo find /var/lib/homeassistant/custom_components/cottage_monitoring -type d -exec chmod 755 {} \; \
    && sudo find /var/lib/homeassistant/custom_components/cottage_monitoring -type f -exec chmod 644 {} \;'
