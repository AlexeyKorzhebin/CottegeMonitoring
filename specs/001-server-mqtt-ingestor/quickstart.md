# Quickstart: Server MQTT Ingestor

## Prerequisites

- Python 3.12+
- Docker & Docker Compose (для инфраструктуры или полного запуска)
- Доступ к MQTT брокеру (или docker-compose поднимает локальный)

---

## Вариант 1: Docker Compose (рекомендуемый для разработки)

```bash
cd server

# Запуск всего стека: app + postgres + timescaledb + redis + mosquitto
docker compose up -d

# Проверка
curl http://localhost:8321/health
curl http://localhost:8321/docs  # Swagger UI
```

Сервисы:
- **app**: http://localhost:8321
- **postgres**: localhost:5432 (user: cottage, db: cottage_monitoring)
- **redis**: localhost:6379
- **mosquitto**: localhost:1883 (dev broker)

```bash
# Логи
docker compose logs -f app

# Остановка
docker compose down
```

---

## Вариант 2: Локальная разработка (Python venv)

```bash
cd server

# Создание виртуального окружения
python3.12 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -e ".[dev]"

# Инфраструктура в Docker
docker compose up -d postgres redis

# Переменные окружения
cp deploy/cottage-monitoring.env .env
# Отредактировать .env: MQTT_HOST, DB_URL, REDIS_URL

# Миграции БД
alembic upgrade head

# Запуск
uvicorn cottage_monitoring.main:app --host 127.0.0.1 --port 8321 --reload
```

---

## Вариант 3: Production (systemd на Ubuntu)

```bash
# 1. Установка зависимостей системы
sudo apt update
sudo apt install -y python3.12 python3.12-venv postgresql redis-server nginx

# 2. TimescaleDB
sudo apt install -y timescaledb-2-postgresql-16
sudo timescaledb-tune
sudo systemctl restart postgresql

# 3. Создание пользователя и директорий
sudo useradd -r -s /bin/false cottage-monitoring
sudo mkdir -p /opt/cottage-monitoring /etc/cottage-monitoring /var/log/cottage-monitoring
sudo chown cottage-monitoring:cottage-monitoring /var/log/cottage-monitoring

# 4. Деплой приложения
sudo cp -r server/ /opt/cottage-monitoring/
cd /opt/cottage-monitoring
sudo python3.12 -m venv venv
sudo venv/bin/pip install .

# 5. Конфигурация
sudo cp deploy/cottage-monitoring.env /etc/cottage-monitoring/
sudo chmod 600 /etc/cottage-monitoring/cottage-monitoring.env
# Отредактировать: MQTT_HOST, MQTT_USER, MQTT_PASSWORD, DB_URL, REDIS_URL

# 6. База данных
sudo -u postgres createuser cottage
sudo -u postgres createdb -O cottage cottage_monitoring
sudo -u postgres psql -d cottage_monitoring -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
cd /opt/cottage-monitoring && sudo -u cottage-monitoring venv/bin/alembic upgrade head

# 7. Systemd
sudo cp deploy/cottage-monitoring.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cottage-monitoring
sudo systemctl start cottage-monitoring

# 8. Nginx
sudo cp deploy/nginx/cottage-monitoring.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/cottage-monitoring.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 9. Проверка
curl http://localhost:8321/health
sudo systemctl status cottage-monitoring
sudo journalctl -u cottage-monitoring -f
```

---

## Вариант 4: Production (Docker на Ubuntu)

```bash
# 1. Установка Docker
curl -fsSL https://get.docker.com | sh

# 2. Деплой
cd server
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 3. Nginx (на хосте)
sudo cp deploy/nginx/cottage-monitoring.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/cottage-monitoring.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Конфигурация (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_HOST` | `localhost` | MQTT broker host |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USER` | — | MQTT username |
| `MQTT_PASSWORD` | — | MQTT password |
| `MQTT_USE_TLS` | `false` | Enable TLS |
| `MQTT_CLIENT_ID` | `cottage-monitoring-server` | MQTT client ID |
| `DB_URL` | `postgresql+asyncpg://cottage:cottage@localhost:5432/cottage_monitoring` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `API_PORT` | `8321` | API listen port |
| `API_HOST` | `0.0.0.0` | API listen host |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_DIR` | `/var/log/cottage-monitoring` | Log files directory |
| `LOG_MAX_BYTES` | `52428800` | Max log file size (50MB) |
| `LOG_BACKUP_COUNT` | `10` | Number of rotated log files |
| `CMD_TIMEOUT_SECONDS` | `60` | Command ack timeout |
| `CMD_MAX_RETRIES` | `2` | Max command retries |

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
open http://localhost:8321/docs

# Prometheus метрики
curl http://localhost:8321/metrics

# Health check
curl http://localhost:8321/health

# Публикация тестового события (mosquitto_pub)
mosquitto_pub -h localhost -t "lm/house-01/v1/events" \
  -m '{"ts":1730000000,"seq":1,"type":"knx.groupwrite","ga":"1/1/1","id":2305,"name":"Свет","datatype":1001,"value":true}'

# Публикация тестового state
mosquitto_pub -h localhost -t "lm/house-01/v1/state/ga/1/1/1" -r \
  -m '{"ts":1730000000,"value":true,"datatype":1001}'
```
