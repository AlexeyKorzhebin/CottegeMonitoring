#!/usr/bin/env bash
# Запуск сервера локально с prod-бэкендом (MQTT, DB, Redis через SSH-туннель).
# Для отладки: curl http://localhost:8323/api/v1/...
# Требуется: ./server/scripts/tunnel-start.sh

set -e
cd "$(dirname "$0")/.."

# Загружаем prod env (нужен правильный DB_URL с паролем)
if [ -f deploy/cottage-monitoring.prod.env ]; then
  set -a
  source deploy/cottage-monitoring.prod.env
  set +a
fi

# Порт 8323 чтобы не конфликтовать с туннелем 8321->elion
export API_PORT=8323

# Debug: пишем логи в workspace (для agent)
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export COTTAGE_DEBUG_LOG="${SCRIPT_DIR}/../.cursor/debug-2b846b.log"

# Туннель даёт localhost:5432, 6379, 1883
exec uvicorn cottage_monitoring.main:app --host 127.0.0.1 --port "$API_PORT"
