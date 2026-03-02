#!/usr/bin/env bash
# Остановка SSH-туннелей к elion (PostgreSQL, Redis, MQTT, REST API).
# Находит и завершает процессы ssh с пересылкой портов к elion.

set -e

PATTERN="ssh.*5432:localhost:5432.*elion"
PIDS=$(pgrep -f "$PATTERN" 2>/dev/null || true)

if [ -z "$PIDS" ]; then
  echo "No elion SSH tunnel processes found."
  exit 0
fi

echo "Stopping elion SSH tunnel(s): $PIDS"
echo "$PIDS" | xargs kill 2>/dev/null || true
echo "Tunnel stopped."
