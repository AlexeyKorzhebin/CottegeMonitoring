#!/usr/bin/env bash
# Запуск SSH-туннеля к elion (PostgreSQL, Redis, MQTT, REST API dev).
# Использует -f для фонового режима. Если туннель уже работает — ничего не делает.

set -e

TUNNEL_CMD="ssh -f -o ExitOnForwardFailure=yes -N \
  -L 5432:localhost:5432 \
  -L 6379:localhost:6379 \
  -L 1883:localhost:1883 \
  -L 8322:localhost:8322 \
  elion"

if pgrep -f "ssh.*5432:localhost:5432.*6379:localhost:6379.*elion" >/dev/null; then
  echo "SSH tunnel to elion already running (ports 5432, 6379, 1883, 8322)"
  exit 0
fi

echo "Starting SSH tunnel to elion..."
$TUNNEL_CMD
echo "Tunnel started. Ports: 5432 (PG), 6379 (Redis), 1883 (MQTT), 8322 (REST dev)"
