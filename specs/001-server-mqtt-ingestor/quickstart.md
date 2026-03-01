# Quickstart: Server MQTT Ingestor

## Сервер

**Хост**: `elion.black-castle.ru` (SSH-алиас: `elion`)
**Доступ**: `ssh elion` (ключи настроены, sudo доступен)
**Сервисы на elion**: PostgreSQL 16 + TimescaleDB, Redis 7, Mosquitto (MQTT broker), nginx

## Prerequisites

- Python 3.12+
- SSH-доступ к серверу: `ssh elion` (ключи уже настроены)
- Docker & Docker Compose (опционально, для тестов на dev-машине)

---

## Вариант 1: Локальная разработка через SSH tunnel (рекомендуемый)

Все сервисы (PostgreSQL, Redis, Mosquitto) работают на `elion`. Dev-машина
подключается к ним через SSH tunnel.

```bash
# 1. SSH tunnel к elion (PostgreSQL + Redis + MQTT)
# Запустить в отдельном терминале (или использовать -f для фонового режима)
ssh -L 5432:localhost:5432 -L 6379:localhost:6379 -L 1883:localhost:1883 elion -N

# 2. Создание виртуального окружения
cd server
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Установка зависимостей
pip install -e ".[dev]"

# 4. Переменные окружения (dev)
cp deploy/cottage-monitoring.dev.env .env
# DB_URL, REDIS_URL, MQTT_HOST уже указывают на localhost (через SSH tunnel)
# MQTT_TOPIC_PREFIX=dev/ — dev-инстанс использует топики dev/lm/+/v1/#

# 5. Миграции БД (dev)
alembic upgrade head

# 6. Запуск
uvicorn cottage_monitoring.main:app --host 127.0.0.1 --port 8322 --reload
```

Сервисы через tunnel:
- **PostgreSQL**: localhost:5432 → elion:5432 (db: **cottage_monitoring_dev**)
- **Redis**: localhost:6379 → elion:6379 (db: 1)
- **MQTT**: localhost:1883 → elion:1883 (prefix: `dev/`)

```bash
# Публикация тестового события (dev-топик)
mosquitto_pub -h localhost -t "dev/lm/house-01/v1/events" \
  -m '{"ts":1730000000,"seq":1,"type":"knx.groupwrite","ga":"1/1/1","id":2305,"name":"Свет","datatype":1001,"value":true}'
```

---

## Вариант 2: Production (Docker + systemd на elion)

Приложение работает как Docker-контейнер, управляемый systemd. Контейнер использует
`--network=host` для доступа к PostgreSQL, Redis и Mosquitto на localhost.

Все команды выполняются на сервере `elion` (`ssh elion`).

```bash
# 1. Установка зависимостей системы (если не установлены)
sudo apt update
sudo apt install -y docker.io nginx mosquitto mosquitto-clients

# 2. PostgreSQL 16 + TimescaleDB (если не установлены)
sudo apt install -y postgresql-16 redis-server
sudo apt install -y timescaledb-2-postgresql-16
sudo timescaledb-tune
sudo systemctl restart postgresql

# 3. Создание директорий
sudo mkdir -p /opt/cottage-monitoring /etc/cottage-monitoring
sudo mkdir -p /var/log/cottage-monitoring/prod /var/log/cottage-monitoring/dev

# 4. Базы данных (dev + production) — обе на elion
sudo -u postgres createuser cottage
sudo -u postgres createdb -O cottage cottage_monitoring       # production
sudo -u postgres createdb -O cottage cottage_monitoring_dev   # dev/staging
sudo -u postgres psql -d cottage_monitoring -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
sudo -u postgres psql -d cottage_monitoring_dev -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

# 5. Деплой приложения (сборка Docker-образа)
sudo cp -r server/ /opt/cottage-monitoring/
cd /opt/cottage-monitoring/server
sudo docker build -t cottage-monitoring:latest -f deploy/Dockerfile .

# 6. Конфигурация
sudo cp deploy/cottage-monitoring.prod.env /etc/cottage-monitoring/
sudo cp deploy/cottage-monitoring.dev.env /etc/cottage-monitoring/
sudo chmod 600 /etc/cottage-monitoring/*.env

# 7. Миграции (обе базы — через одноразовые контейнеры)
sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  cottage-monitoring:latest alembic upgrade head

sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.dev.env \
  cottage-monitoring:latest alembic upgrade head

# 8. Systemd (оба инстанса)
sudo cp deploy/cottage-monitoring.service /etc/systemd/system/
sudo cp deploy/cottage-monitoring-dev.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cottage-monitoring
sudo systemctl start cottage-monitoring
# Dev-инстанс (опционально):
# sudo systemctl enable cottage-monitoring-dev
# sudo systemctl start cottage-monitoring-dev

# 9. Nginx
sudo cp deploy/nginx/cottage-monitoring.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/cottage-monitoring.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 10. Проверка
curl http://localhost:8321/health
sudo systemctl status cottage-monitoring
sudo journalctl -u cottage-monitoring -f
sudo docker logs cottage-monitoring
```

---

## Две базы данных + два MQTT-потока: dev и production

На сервере `elion` создаются **две раздельные базы** PostgreSQL + TimescaleDB
и используются **раздельные MQTT-топики** для полной изоляции:

| | Production | Dev/Staging |
|--|-----------|-------------|
| **БД** | `cottage_monitoring` | `cottage_monitoring_dev` |
| **Redis DB** | `redis://localhost:6379/0` | `redis://localhost:6379/1` |
| **MQTT prefix** | *(пусто)* → `lm/+/v1/#` | `dev/` → `dev/lm/+/v1/#` |
| **MQTT Client ID** | `cottage-monitoring-server` | `cottage-monitoring-dev` |
| **Порт API** | 8321 | 8322 |
| **Env-файл** | `cottage-monitoring.prod.env` | `cottage-monitoring.dev.env` |

Это позволяет:
- Безопасно тестировать миграции и новый код на dev-базе, не затрагивая production
- Запускать параллельно dev- и prod-инстанс сервиса (на разных портах)
- Dev-инстанс обрабатывает только dev-топики — реальные данные от контроллеров изолированы
- Заливать тестовые данные через `dev/lm/...` без риска для production

### Параллельный запуск на elion (два Docker-контейнера через systemd)

```bash
# Production (порт 8321, prod DB, MQTT без префикса)
sudo systemctl start cottage-monitoring

# Dev (порт 8322, dev DB, MQTT с префиксом dev/)
sudo systemctl start cottage-monitoring-dev

# Статус контейнеров
sudo docker ps --filter "name=cottage-monitoring"
```

### Миграции для каждой базы (на elion, через Docker)

```bash
# Production
sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  cottage-monitoring:latest alembic upgrade head

# Dev
sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.dev.env \
  cottage-monitoring:latest alembic upgrade head
```

### Обновление приложения (на elion)

```bash
cd /opt/cottage-monitoring/server
sudo git pull  # или sudo cp -r ...
sudo docker build -t cottage-monitoring:latest -f deploy/Dockerfile .
# Миграции (если есть новые)
sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  cottage-monitoring:latest alembic upgrade head
# Перезапуск
sudo systemctl restart cottage-monitoring
sudo systemctl restart cottage-monitoring-dev  # если dev запущен
```

---

## Конфигурация (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `dev` | Окружение: `dev` / `production` |
| `MQTT_HOST` | `localhost` | MQTT broker host (localhost на elion, localhost через SSH tunnel с dev-машины) |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USER` | — | MQTT username |
| `MQTT_PASSWORD` | — | MQTT password |
| `MQTT_USE_TLS` | `false` | Enable TLS (false для localhost, true для внешних подключений) |
| `MQTT_CLIENT_ID` | `cottage-monitoring-server` | MQTT client ID (разные для dev/prod!) |
| `MQTT_TOPIC_PREFIX` | *(пусто)* | Префикс MQTT-топиков. `dev/` для dev, пусто для prod |
| `DB_URL` | `postgresql+asyncpg://cottage:cottage@localhost:5432/cottage_monitoring_dev` | PostgreSQL connection (localhost — на elion или через SSH tunnel) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection (localhost — на elion или через SSH tunnel) |
| `API_PORT` | `8321` | API listen port |
| `API_HOST` | `0.0.0.0` | API listen host |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_DIR` | `/var/log/cottage-monitoring` | Log files directory |
| `LOG_MAX_BYTES` | `52428800` | Max log file size (50MB) |
| `LOG_BACKUP_COUNT` | `10` | Number of rotated log files |
| `CMD_TIMEOUT_SECONDS` | `60` | Command ack timeout |
| `CMD_MAX_RETRIES` | `2` | Max command retries |

### Env-файлы

**`cottage-monitoring.dev.env`** (dev-инстанс на elion или через SSH tunnel):
```env
ENV=dev
DB_URL=postgresql+asyncpg://cottage:cottage@localhost:5432/cottage_monitoring_dev
REDIS_URL=redis://localhost:6379/1
MQTT_HOST=localhost
MQTT_USE_TLS=false
MQTT_CLIENT_ID=cottage-monitoring-dev
MQTT_TOPIC_PREFIX=dev/
LOG_LEVEL=DEBUG
API_PORT=8322
```

**`cottage-monitoring.prod.env`** (prod-инстанс на elion):
```env
ENV=production
DB_URL=postgresql+asyncpg://cottage:<STRONG_PASSWORD>@localhost:5432/cottage_monitoring
REDIS_URL=redis://localhost:6379/0
MQTT_HOST=localhost
MQTT_USE_TLS=false
MQTT_CLIENT_ID=cottage-monitoring-server
MQTT_TOPIC_PREFIX=
LOG_LEVEL=INFO
API_PORT=8321
```

---

## Тесты

```bash
cd server

# Unit-тесты
pytest tests/unit/ -v

# Integration-тесты (требуют Docker для testcontainers)
pytest tests/integration/ -v

# Contract-тесты API
pytest tests/contract/ -v

# Все тесты
pytest -v --cov=cottage_monitoring

# Линтинг
ruff check src/ tests/
mypy src/
```

---

## Полезные команды

```bash
# Swagger UI
open http://localhost:8321/docs      # prod
open http://localhost:8322/docs      # dev

# Health check
curl http://localhost:8321/health    # prod
curl http://localhost:8322/health    # dev

# Prometheus метрики
curl http://localhost:8321/metrics

# --- Dev-топики (префикс dev/) ---

# Публикация тестового события (dev)
mosquitto_pub -h localhost -t "dev/lm/house-01/v1/events" \
  -m '{"ts":1730000000,"seq":1,"type":"knx.groupwrite","ga":"1/1/1","id":2305,"name":"Свет","datatype":1001,"value":true}'

# Публикация тестового state (dev)
mosquitto_pub -h localhost -t "dev/lm/house-01/v1/state/ga/1/1/1" -r \
  -m '{"ts":1730000000,"value":true,"datatype":1001}'

# --- Prod-топики (без префикса, реальные данные от контроллеров) ---

# Подписка на все prod-сообщения (мониторинг)
mosquitto_sub -h localhost -t "lm/+/v1/#" -v
```
