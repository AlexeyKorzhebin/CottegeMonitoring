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
# MQTT_TOPIC_PREFIX=dev/ — dev-инстанс использует топики dev/cm/+/+/v1/#

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
mosquitto_pub -h localhost -t "dev/cm/house-01/lm-main/v1/events" \
  -m '{"ts":1730000000,"seq":1,"type":"knx.groupwrite","ga":"1/1/1","id":2305,"name":"Свет","datatype":1001,"value":true}'
```

---

## Вариант 2: Production (Docker + systemd на elion)

Приложение работает как Docker-контейнер, управляемый systemd. Контейнер использует
bridge + `host.docker.internal:host-gateway` (см. `deploy/elion-bind-docker0.sh`); API публикуется на `127.0.0.1:8321`.

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

# 5. Деплой приложения — НЕ собирать на elion.
# Локально: docker build --platform linux/amd64 -t cottage-monitoring:0.2.4 …
# Затем: docker save | ssh elion docker load (см. секцию «Обновление приложения»).

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
| **MQTT prefix** | *(пусто)* → `cm/+/+/v1/#` | `dev/` → `dev/cm/+/+/v1/#` |
| **MQTT Client ID** | `cottage-monitoring-server` | `cottage-monitoring-dev` |
| **Порт API** | 8321 | 8322 |
| **Env-файл** | `cottage-monitoring.prod.env` | `cottage-monitoring.dev.env` |

Это позволяет:
- Безопасно тестировать миграции и новый код на dev-базе, не затрагивая production
- Запускать параллельно dev- и prod-инстанс сервиса (на разных портах)
- Dev-инстанс обрабатывает только dev-топики — реальные данные от контроллеров изолированы
- Заливать тестовые данные через `dev/cm/...` без риска для production

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

### Обновление приложения (локальная сборка → elion)

По правилам репозитория: **код на сервер не копировать**. Сборка на Mac/CI, на elion только load/pull + restart.

```bash
# Локально (из server/)
docker build --platform linux/amd64 -t cottage-monitoring:0.2.5 -f deploy/Dockerfile .
docker save cottage-monitoring:0.2.5 | ssh elion 'sudo docker load'
# Один раз на elion: sudo bash deploy/elion-bind-docker0.sh
# Env: host.docker.internal; systemd: bridge + -p 127.0.0.1:8321:8321
ssh elion 'sudo systemctl daemon-reload && sudo systemctl restart cottage-monitoring'
```

Сеть: **bridge** + `host.docker.internal:host-gateway` (не `--network=host`).

Текущий pin: **`cottage-monitoring:0.2.6`** (`server/deploy/IMAGE_PIN.yaml`).

### Dry-run команд (без MQTT)

Заголовок `X-Cottage-Dry-Run: 1` на `/mcp` или `/api/v1`: `send_command` пишет запись со `status=dry_run` и **не публикует** в MQTT. Для бенчей агентов: mcporter alias `cottage-dry` + `server/scripts/bench_mcp_models/run_bench.py --e2e`.

```bash
# на elion (openclaw)
python3 run_bench.py --e2e --mcp-alias cottage-dry --out results/e2e.json
```


---

## Production security / ops (аудит 2026-07, статус)

### Сделано в 0.2.6 + live elion

| Пункт | Статус |
|-------|--------|
| `X-Cottage-Dry-Run` | MCP/API: resolve+DB, status=`dry_run`, MQTT skip |
| MCP model bench e2e | `cottage-dry` + `run_bench.py --e2e` (Caila, в т.ч. gpt-5.6-sol) |

### Сделано в 0.2.5 + live elion

| Тема | Статус |
|------|--------|
| `AUTH_REQUIRED` в prod | `true` (+ fail-fast если ENV=production и auth off) |
| Write-scope на REST/MCP mutating | включено |
| Валидация значений команд | `command_validation.py` (тип/батч) |
| MCP rate-limit | fail-closed (in-memory fallback) |
| `/docs`, `/openapi` в prod | отключены в приложении |
| MQTT ACL | `lm_estate` → только `cm/house/#` |
| TLS cert mosquitto | certbot + short-chain hook; check: `server/scripts/check_mosquitto_cert.sh` |
| API listen | `127.0.0.1:8321/8322` |
| Persistent MQTT publisher | lifespan `start_publisher` |
| Events retention/compression | 365d retention, compress after 7d (alembic 006) |
| Event QoS1 dedup | unique `(house_id,device_id,seq,ts)` (alembic 007) |
| Ingest lag gauge | `ingestor_lag_current_seconds` |
| GA helpers | `utils/ga.py` (slash API / dash storage) |
| Docker non-root | uid/gid 999, `--cap-drop=ALL` |
| Docker network | bridge + `host.docker.internal:host-gateway`; API `-p 127.0.0.1:8321:8321` |
| Host deps for bridge | PG/Redis/MQTT:1883 also on `172.17.0.1` (`elion-bind-docker0.sh`) |
| Telegram alerts secrets | `/etc/cottage-monitoring/telegram.env` |
| Grafana dashboards + alerts | `server/deploy/grafana/` — quickstart § Grafana, **R-015** |

### Клиент LM

- `mqtt_tls_verify` + `mqtt_cafile` (ISRG Root X1 в `cm-client/certs/`)
- Проверка cert брокера: `server/scripts/check_mosquitto_cert.sh`

### Отложено

- Секреты: не коммитить пароли в git — см. **R-012** (домашний уровень, без обязательной ротации).

### MCP: управляемый тест команд (холл 2 этаж, 2026-07)

Проверка цепочки **MCP → MQTT → LM → ack → traces** на **dev-инстансе** (`:8322`, `cottage_monitoring_dev`).

**Важно:** физический LM в `env_mode=prod` подписан на `cm/house/lm-main/v1/cmd` (без префикса). Dev-контейнер по умолчанию публикует в `dev/cm/...` — **команды до LM не доходят**. Для живого теста на шину временно `MQTT_TOPIC_PREFIX=` (пусто), после теста вернуть `dev/`.

```bash
# на elion: MCP set_commands ON → sleep 30 → OFF (см. research R-011)
# параллельно: mosquitto_sub -t 'cm/house/lm-main/v1/cmd' -t 'cm/house/lm-main/v1/cmd/#'
```

**Инструменты MCP:** `set_commands` с явным GA надёжнее, чем `set_light` по имени, если в dev-БД нет полной схемы `objects` (у `house` было 2 объекта → `set_light` → 404).

**Трейсы** (`operation_traces`, `trace_persist=true` на dev по умолчанию):

| kind | ref | duration_ms | смысл |
|------|-----|-------------|--------|
| `mcp_tool` | `set_commands` | ~20–120 | время MCP-вызова (резолв + постановка) |
| `command_sent` | `request_id` | ~1–10 | публикация в MQTT |
| `command_ack` | `request_id` | ≈ RTT | от `ts_sent` до ack |

**RTT** (Round-Trip Time) = `ts_ack − ts_sent` в таблице `commands`. Пример живого теста: ON ~2.5 с, OFF ~0.5 с. Отдельных таймингов «только сеть» / «только grp.write» нет — они внутри `command_ack`.

**API keys:** `cottage-create-api-key` внутри контейнера; временные ключи после теста — `revoked_at=now()`. Бот (OpenClaw) хранит prod/dev ключи в `~/.openclaw/secrets/` на elion (не в git).

### MCP model bench (Caila × cottage tools)

Скрипт: `server/scripts/bench_mcp_models/` (на elion: `~openclaw/.openclaw/workspace/cottage-mcp-bench/`).

| Режим | Команда | MQTT |
|-------|---------|------|
| model-only | `python3 run_bench.py` | нет |
| e2e dry-run | `python3 run_bench.py --e2e --mcp-alias cottage-dry` | нет (`X-Cottage-Dry-Run`) |

**Вывод (R-014):** для dial-команд дома — отдельный OpenClaw-агент на **gemini-3.5-flash** с минимальным контекстом; `main` на sol оставить для общего чата. На одинаковом коротком промпте Flash ≈ **2×** быстрее sol; vs текущий main с большим cache выигрыш обычно **≥2×** (часто больше). Детали и цифры — `specs/001-server-mqtt-ingestor/research.md` **R-014**.

```bash
# на elion от пользователя openclaw
set -a; source ~/.openclaw/secrets/llms.env; set +a
export PATH=$HOME/.npm-global/bin:$PATH
cd ~/.openclaw/workspace/cottage-mcp-bench
python3 run_bench.py --e2e --mcp-alias cottage-dry --out results/latest.json
```

### Автообновление сертификата MQTT

**Да.** certbot.timer + `preferred_chain = ISRG Root X1` + `/etc/letsencrypt/renewal-hooks/deploy/10-mosquitto.sh`.

**Мониторинг:** ежедневно `check_mosquitto_cert_alert.sh` (2 PEM + запас ≥14 дней). При FAIL — syslog и **Telegram** (`/etc/cottage-monitoring/telegram.env`). Лог: `/var/log/cottage-monitoring/cert-check.log`.

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
| `TRACE_PERSIST` | auto (`true` if `ENV=dev`) | Писать `operation_traces` (MCP/command timing) |

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
mosquitto_pub -h localhost -t "dev/cm/house-01/lm-main/v1/events" \
  -m '{"ts":1730000000,"seq":1,"type":"knx.groupwrite","ga":"1/1/1","id":2305,"name":"Свет","datatype":1001,"value":true}'

# Публикация тестового state (dev)
mosquitto_pub -h localhost -t "dev/cm/house-01/lm-main/v1/state/ga/1/1/1" -r \
  -m '{"ts":1730000000,"value":true,"datatype":1001}'

# --- Prod-топики (без префикса, реальные данные от контроллеров) ---

# Подписка на все prod-сообщения (мониторинг)
mosquitto_sub -h localhost -t "cm/+/+/v1/#" -v
```

---

## Grafana (elion) — телеметрия дома

**Не** Prometheus-метрики приложения (`/metrics`, FR-043..045), а дашборды по
данным MQTT→БД (`events` / `current_state` / `objects`). Код и runbook:
`server/deploy/grafana/` (генератор JSON + provisioning). Решение: **R-015**.

### URL

База: `https://elion.black-castle.ru/grafana/` (за nginx).

| UID | Title | Содержание |
|-----|-------|------------|
| `cottage-overview` | Overview | Online, мощность, kWh, свет/ТП снимки |
| `cottage-energy` | Electricity | P/Q/U/I/PF/Hz, суточные/часовые kWh |
| `cottage-climate` | Climate | Воздух/влажность, погода, полы |
| `cottage-lights` | Lights | Статусы света + история |
| `cottage-batteries` | Batteries | Zigbee battery % |
| `cottage-lm-load` | LM Load | loadavg LM: GA `34/1/6` (1м), `34/1/7` (5м), `34/1/8` (15м) |

Папка Grafana: **Cottage** (`folderUid=ffsa6lrlntse8b`).
Datasource: PostgreSQL UID `cottage-monitoring-pg` → БД `cottage_monitoring`,
роль `cottage_grafana` (SELECT-only).

### Деплой дашбордов

```bash
./server/deploy/grafana/deploy.sh
```

- Генерирует JSON из `generate_dashboards.py` → `dashboards/cottage_*.json`
- На elion: provisioning datasource + файлы в `/var/lib/grafana/dashboards/cottage`
- Секрет пароля БД: `/etc/cottage-monitoring/grafana-db.password` (не в git)

После правок генератора — снова `deploy.sh` (не править JSON на сервере вручную).

### Алерты (Telegram)

```bash
./server/deploy/grafana/deploy_alerts.sh
```

Секреты: `/etc/cottage-monitoring/telegram.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
Contact point `cottage-telegram`, route matcher `team=cottage`.

| UID | Условие | for | severity |
|-----|---------|-----|----------|
| `cottage-house-stale` | дом не online / `last_seen` >15m | 5m | critical |
| `cottage-lm-load15-high` | GA `34/1/8` (load15) **> 2.0** | 10m | warning |

`cottage-lm-load15-high`: `noDataState=OK` (отсутствие точек не спамит — за stale отвечает другой алерт).

### Cursor / MCP

Grafana на elion — OSS. Для агента: MCP `user-grafana` →
`https://elion.black-castle.ru/grafana`, токен service account на elion
`/etc/cottage-monitoring/grafana-mcp.token` (локально `~/.config/grafana-mcp/token`).
Подробнее: `server/deploy/grafana/README.md`.

### SQL-заметки

- В `current_state.ga` часто dash-форма (`1-2-3`); в запросах:
  `replace(cs.ga,'-','/') = o.ga`.
- Timeseries: `$__timeGroupAlias(e.ts, $__interval)` по hypertable `events`
  (не `NULL`-gapfill на длинных диапазонах — ломает браузер).
- Loadavg пишется LM в `34/1/6..8` и попадает в prod `events` (~раз в минуту для load1).
