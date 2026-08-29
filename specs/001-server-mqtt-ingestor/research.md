# Research: Server MQTT Ingestor

**Date**: 2026-03-01 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## R-001: Классификация объектов из objects.json

### Контекст

Анализ `docs/objects.json` — реальная выгрузка ~150 объектов с контроллера LogicMachine.
Это количество на один контроллер/устройство — в доме может быть несколько контроллеров.
Необходимо классифицировать объекты по семантике тегов (`control` / `status`), типам
данных и назначению: **мгновенные** (snapshot) vs **временные ряды** (time-series).

### Теги и их семантика

| Тег | Значение |
|-----|----------|
| `control` | Запись в объект вызывает действие на устройстве. Значение **не обязательно** отражает реальное состояние |
| `status` | Реальное состояние устройства (обратная связь от актуатора/датчика) |
| `light` | Освещение |
| `heat` | Отопление / тёплые полы |
| `temp` | Температура |
| `setpoint` | Уставка температуры |
| `meter` | Электросчётчик |
| `weather` / `outside` | Погодные данные / уличные объекты |
| `humidity` | Влажность |
| `zigbee` / `zb_sensor` | Zigbee-устройства и датчики |
| `monitoring` | Диагностические/мониторинговые объекты |
| `battery` | Уровень заряда батареи |
| `occupancy` | Датчик присутствия (PIR) |
| `illuminance` | Датчик освещённости |
| `wind` | Ветер |
| `pressure_mm` | Атмосферное давление |
| `1floor` / `2floor` / `floor1` / `floor2` | Привязка к этажу |
| `auto` | Автоматический режим управления |

### Классификация объектов

#### 1. Мгновенные значения (Instant/Snapshot)

Показывают текущее состояние "прямо сейчас". Используются для дашбордов, оповещений, UI.

| GA Group | Название | Теги | Datatype | Тип значения | Кол-во |
|----------|----------|------|----------|-------------|--------|
| 1/1/* | Свет (управление) | `control, light` | 1001 (bool) | ON/OFF | 20 |
| 1/2/* | Свет (статус) | `status, light` | 1001 (bool) | ON/OFF реальное | 20 |
| 1/3/* | Температура помещений | `heat, temp` | 9001 (float16) | °C | 14 |
| 1/4/* | Тёплый пол (управление) | `control, heat` | 1001 (bool) | ON/OFF | 14 |
| 1/5/* | Тёплый пол (статус) | `status, heat` | 1001 (bool) | ON/OFF реальное | 14 |
| 1/6/* | Уставка температуры | `heat, setpoint, temp` | 9001 (float16) | °C | 15 |
| 1/7/1 | Авто-режим отопления | `auto, heat` | 1001 (bool) | ON/OFF | 1 |
| 32/1/1-10 | Напряжение, частота, углы | `meter` | 14/8 (float32/int) | V, Hz, ° | 10 |
| 32/1/11-16,19-24,27-32 | Ток, мощность, PF | `meter` | 14 (float32) | A, W, VAR, VA | 18 |
| 32/1/35-43 | Суммарные мощности, PF, углы | `meter` | 14 (float32) | W, VAR, VA | 9 |
| 32/5/* | Погода | `weather, outside` | разные | °C, %, мм, м/с, текст | 8 |
| 33/1/* | Zigbee датчики (температура, влажность, батарея) | `zb_sensor` | 9001/5 | °C, %, % | 27 |
| 32/7/13-18 | PIR датчик | `occupancy, zigbee` | разные | bool, lux, %, int | 6 |
| 32/6/2-3 | Z-реле проектор | `control/status, zigbee` | 1001 (bool) | ON/OFF | 2 |
| 34/1/* | ТП диагностика | `monitoring` | 255 (string) | Текст | 5 |
| 32/1/44 | Diagnostic text | `monitoring` | 255 (string) | Текст | 1 |
| 32/1/50-56 | Статусы устройств (rd2-rd5) | — | 1 (bool) | ON/OFF | 5 |

#### 2. Временные ряды (Time-Series)

Значения, для которых важна **динамика изменений** во времени. Хранятся в TimescaleDB hypertable для графиков и аналитики.

| GA Group | Название | Теги | Datatype | Единицы | Тип ряда | Кол-во |
|----------|----------|------|----------|---------|---------|--------|
| 1/3/* | Температура помещений | `heat, temp` | 9001 | °C | Gauge (мгновенное + тренд) | 14 |
| 33/1/1,4,7,10,13,16,19,22,25 | Zigbee температура | `zb_sensor, temperature` | 9001 | °C | Gauge | 9 |
| 33/1/2,5,8,11,14,17,20,23,26 | Zigbee влажность | `zb_sensor, humidity` | 5 | % | Gauge | 9 |
| 32/5/1-2 | Уличная температура | `weather, temp, outside` | 9001 | °C | Gauge | 2 |
| 32/5/3 | Влажность | `humidity, outside, weather` | 5001 | % | Gauge | 1 |
| 32/5/4 | Давление | `pressure_mm, weather` | 7 | мм рт.ст. | Gauge | 1 |
| 32/5/6-7 | Скорость ветра | `wind, weather` | 9 | м/с | Gauge | 2 |
| 32/1/13,21,29 | Активная мощность (P) L1/L2/L3 | `meter` | 14 | W | Gauge (профиль нагрузки) | 3 |
| 32/1/35 | Суммарная активная мощность | `meter` | 14 | W | Gauge | 1 |
| 32/1/17,25,33 | Активная энергия (AP) L1/L2/L3 | `meter` | 14 | kWh | Counter (накопительный) | 3 |
| 32/1/39 | Суммарная активная энергия | `meter` | 14 | kWh | Counter | 1 |
| 32/1/18,26,34 | Реактивная энергия (RP) L1/L2/L3 | `meter` | 14 | kVARh | Counter | 3 |
| 32/1/40 | Суммарная реактивная энергия | `meter` | 14 | kVARh | Counter | 1 |
| 32/1/57 | Потребление за час | `meter` | 14 | kWh | Delta (производная) | 1 |
| 32/1/58 | Потребление за сутки | `meter` | 14 | kWh | Delta | 1 |
| 32/1/59 | Потребление суммарно | `meter` | 14 | kWh | Counter | 1 |
| 32/6/4 | Энергия на тёплые полы | `heat` | 7 | W | Gauge | 1 |

#### 3. Типы временных рядов

- **Gauge** — мгновенное значение, которое может расти и уменьшаться (температура, мощность, влажность). Хранится as-is.
- **Counter** — монотонно возрастающий счётчик (kWh, kVARh). Для аналитики вычисляется delta (derivative).
- **Delta** — уже вычисленная разность (потребление за час/сутки). Хранится as-is.

### Решение

- Все events записываются в TimescaleDB hypertable для единообразной обработки.
- Объекты с тегами `temp`, `meter`, `humidity`, `weather`, `wind`, `pressure_mm` маркируются `is_timeseries=true` в таблице objects для UI-подсказок.
- Gauge/Counter/Delta тип определяется на уровне API по тегам и единицам измерения.
- `control` объекты не включаются в time-series по умолчанию (их значение ненадёжно). Только `status` объекты и сенсорные данные.

### Альтернативы рассмотрены

- Хранить только events без маркировки → отвергнуто: без маркировки UI не может автоматически строить графики для нужных объектов.
- Разделять потоки ingestion для мгновенных и временных рядов → отвергнуто: усложнение без выгоды, единый event pipeline достаточно.

---

## R-002: Redis для кеширования текущего состояния

### Контекст

Principle IV требует real-time доступ к актуальному срезу. При 10 домах × N контроллеров × ~150 объектов на контроллер записей state. API должен отвечать за <200ms.

### Решение

**Использовать Redis как read-through cache для current state.**

- Ключ: `state:{house_id}:{ga}` → JSON `{ts, value, datatype}`
- При получении `state/ga/*` из MQTT: записать в PostgreSQL (upsert) + записать в Redis (SET).
- При API запросе GET state: читать из Redis; fallback на PostgreSQL при cache miss.
- TTL: без expire (retained state обновляется при изменении, не устаревает).
- HSET вариант: `state:{house_id}` → hash field `{ga}` → value JSON — эффективнее для batch-запросов (HGETALL).

### Обоснование

- PostgreSQL upsert на 1500 объектов: ~50-100ms (batch).
- Redis HGETALL на 150 объектов: ~1-2ms.
- Разница в 50x оправдывает дополнительный компонент.

### Альтернативы рассмотрены

- Только PostgreSQL: <200ms достижимо для одного дома, но для 10 домов batch-запросы будут медленнее.
  Отвергнуто для production, но PostgreSQL fallback сохраняется.
- In-memory dict в Python: теряется при рестарте; не переживает horizontal scaling.
  Отвергнуто.

---

## R-003: FastAPI как API-фреймворк

### Решение

**FastAPI** — async Python web framework.

- Автогенерация OpenAPI spec (Swagger UI из коробки).
- Нативная поддержка Pydantic v2 для валидации.
- Async — работает в одном event loop с aiomqtt.
- Широкая экосистема (prometheus-fastapi-instrumentator, etc.).
- Совместим с MCP-серверами (REST endpoints).

### Альтернативы

- aiohttp: менее удобен для REST API, нет автогенерации OpenAPI. Отвергнуто.
- Django: sync by default, тяжеловесен для данной задачи. Отвергнуто.
- Flask: нет async, нет автогенерации OpenAPI. Отвергнуто.

---

## R-004: Деплой на elion.black-castle.ru

### Контекст

Все сервисы размещаются на одном сервере `elion.black-castle.ru` (SSH-алиас: `elion`,
доступ `ssh elion` с sudo). PostgreSQL, Redis, Mosquitto работают как системные сервисы.
Приложение подключается к ним через `localhost`.

Для локальной разработки — SSH tunnel к elion:
```bash
ssh -L 5432:localhost:5432 -L 6379:localhost:6379 -L 1883:localhost:1883 elion -N
```

### Решение

**Основной вариант** — systemd на elion. Docker используется опционально для тестов.

#### Dockerfile (для тестов / CI)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
CMD ["uvicorn", "cottage_monitoring.main:app", "--host", "0.0.0.0", "--port", "8321"]
```

#### Systemd + Docker (два инстанса на elion)

Оба инстанса (prod и dev) запускаются как Docker-контейнеры, управляемые systemd.
Сеть: **bridge** + `--add-host=host.docker.internal:host-gateway`; API `-p 127.0.0.1:8321:8321`.
Хостовые PG/Redis/MQTT:1883 слушают также `172.17.0.1` (`deploy/elion-bind-docker0.sh` + `route_localnet`/UFW).

```ini
# cottage-monitoring.service (PRODUCTION — порт 8321)
[Unit]
Description=CottageMonitoring MQTT Ingestor (production)
After=network.target docker.service postgresql.service redis.service
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/docker stop cottage-monitoring
ExecStartPre=-/usr/bin/docker rm cottage-monitoring
ExecStart=/usr/bin/docker run --name cottage-monitoring \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:8321:8321 \
  --user 999:999 --cap-drop=ALL --security-opt=no-new-privileges:true \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  -e API_HOST=0.0.0.0 \
  -v /var/log/cottage-monitoring/prod:/var/log/cottage-monitoring \
  cottage-monitoring:0.2.5
ExecStop=/usr/bin/docker stop cottage-monitoring
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```ini
# cottage-monitoring-dev.service (DEV — порт 8322)
[Unit]
Description=CottageMonitoring MQTT Ingestor (dev)
After=network.target docker.service postgresql.service redis.service
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/docker stop cottage-monitoring-dev
ExecStartPre=-/usr/bin/docker rm cottage-monitoring-dev
ExecStart=/usr/bin/docker run --name cottage-monitoring-dev \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:8322:8322 \
  --user 999:999 --cap-drop=ALL --security-opt=no-new-privileges:true \
  --env-file /etc/cottage-monitoring/cottage-monitoring.dev.env \
  -e API_HOST=0.0.0.0 \
  -v /var/log/cottage-monitoring/dev:/var/log/cottage-monitoring \
  cottage-monitoring:0.2.5
ExecStop=/usr/bin/docker stop cottage-monitoring-dev
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### Сборка и деплой образов

```bash
# Локально: docker build --platform linux/amd64 … → docker save | ssh elion docker load
# Один раз на elion: sudo bash deploy/elion-bind-docker0.sh

# Миграции (через одноразовый контейнер с host-gateway)
docker run --rm --add-host=host.docker.internal:host-gateway \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  cottage-monitoring:0.2.5 alembic upgrade head

docker run --rm --add-host=host.docker.internal:host-gateway \
  --env-file /etc/cottage-monitoring/cottage-monitoring.dev.env \
  cottage-monitoring:0.2.5 alembic upgrade head
```

**Ключевые решения**:
- bridge + `host.docker.internal:host-gateway` (не `--network=host`)
- API только на host loopback: `-p 127.0.0.1:8321:8321`
- PG/Redis/MQTT:1883 дополнительно на `172.17.0.1` + `route_localnet`/UFW docker0

### Обоснование

- Docker: единый артефакт для prod, dev и CI — одинаковая среда везде.
- Systemd: управление жизненным циклом контейнеров (restart, logging, boot).
- bridge + host-gateway: изоляция контейнера при доступе к хостовым PG/Redis/MQTT.
- Две базы + два MQTT-префикса: полная изоляция dev от production на одном сервере.
- SSH tunnel: простой способ подключения с dev-машины без VPN.

---

## R-005: Лучшие практики логирования в файлы

### Решение

**structlog** — структурированное логирование с JSON-выводом.

#### Конфигурация

1. **Два handler'а**: stdout (для Docker/journald) + RotatingFileHandler (для файлов).
2. **Формат**: JSON lines — совместим с ELK, Loki, grep/jq.
3. **Ротация**: `RotatingFileHandler` с `maxBytes=50MB`, `backupCount=10` (итого ~500MB max).
4. **Уровни**: `INFO` по умолчанию, `DEBUG` через env `LOG_LEVEL`.
5. **Контекстные поля**: `ts`, `level`, `logger`, `house_id`, `message_type`, `request_id`.

#### Структура файлов логов

```text
/var/log/cottage-monitoring/
├── app.log          # Основной лог (INFO+)
├── app.log.1        # Ротированные копии
├── app.log.2
├── mqtt.log         # MQTT-специфичные сообщения
├── mqtt.log.1
├── access.log       # HTTP access log (uvicorn)
└── access.log.1
```

#### Лучшие практики

- **Не логировать payload целиком** (может содержать много данных). Логировать house_id + ga + message_type.
- **Структурированные поля** вместо форматированных строк (`log.info("state_updated", house_id=h, ga=ga)` вместо `log.info(f"Updated state for {h}/{ga}")`).
- **Correlation ID** (request_id) для отслеживания команд через весь pipeline.
- **Ротация по размеру** (не по времени) — предсказуемый размер диска.
- **Отдельный логгер для MQTT** — позволяет настроить уровень отдельно.
- **Docker**: stdout + structlog, ротация через Docker logging driver.
- **Systemd**: journal + файлы (RotatingFileHandler). journal для real-time мониторинга, файлы для долгосрочного хранения.

### Альтернативы

- python-json-logger: менее гибкий, нет процессоров. Отвергнуто.
- loguru: популярный, но менее стандартный для enterprise. Рассмотрен как fallback.
- Только stdout (Docker): недостаточно для systemd-деплоя. Нужны оба варианта.

---

## R-006: Nginx reverse proxy на elion

### Решение

Сервис на порту **8321** (prod) / **8322** (dev) за nginx на `elion.black-castle.ru`.

#### Конфигурация nginx

```nginx
# Production API (порт 8321)
upstream cottage_monitoring_prod {
    server 127.0.0.1:8321;
}

# Dev API (порт 8322)
upstream cottage_monitoring_dev {
    server 127.0.0.1:8322;
}

# --- Production ---
server {
    listen 80;
    server_name monitoring.black-castle.ru;

    location /api/ {
        proxy_pass http://cottage_monitoring_prod;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /metrics {
        proxy_pass http://cottage_monitoring_prod;
        proxy_set_header Host $host;
        allow 127.0.0.1;
        allow 10.0.0.0/8;
        deny all;
    }

    location /health {
        proxy_pass http://cottage_monitoring_prod;
    }

    location /docs {
        proxy_pass http://cottage_monitoring_prod;
    }

    location /openapi.json {
        proxy_pass http://cottage_monitoring_prod;
    }
}

# --- Dev ---
server {
    listen 80;
    server_name monitoring-dev.black-castle.ru;

    location / {
        proxy_pass http://cottage_monitoring_dev;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

### Обоснование выбора порта 8321

- Не занят стандартными сервисами.
- Достаточно высокий, чтобы не конфликтовать с другими проектами на elion.
- Легко запоминается (8-3-2-1 обратный отсчёт).

---

## R-007: Async MQTT клиент

### Решение

**aiomqtt** (обёртка над paho-mqtt с asyncio).

- Работает в одном event loop с FastAPI (uvicorn).
- Поддерживает TLS, авторизация логин/пароль.
- Reconnect с exponential backoff (реализуем обёртку).
- QoS 0/1 поддержка.

### Архитектура MQTT + FastAPI

```
uvicorn event loop
├── FastAPI (HTTP requests)
├── aiomqtt subscriber (background task)
│   └── message dispatcher
│       ├── state handler → Redis + PostgreSQL
│       ├── event handler → PostgreSQL (TimescaleDB)
│       ├── meta handler → PostgreSQL (schema registry)
│       ├── status handler → PostgreSQL + Redis (house status)
│       ├── ack handler → PostgreSQL (command update)
│       └── rpc handler → PostgreSQL
└── command retry scheduler (asyncio.Task)
```

MQTT subscriber запускается как background task в FastAPI lifespan.
При отключении от брокера — автоматический reconnect с exponential backoff (1s, 2s, 4s, ..., max 30s).

### Альтернативы

- paho-mqtt (sync): потребовал бы отдельный thread, усложняет взаимодействие. Отвергнуто.
- gmqtt: менее поддерживаемый. Отвергнуто.
- asyncio-mqtt (старое название aiomqtt): это и есть aiomqtt.

---

## R-008: PostgreSQL + TimescaleDB

### Решение

- PostgreSQL 16 для всех таблиц.
- TimescaleDB для таблицы `events` — hypertable с партиционированием по `ts`.
- Alembic для миграций.
- asyncpg (через SQLAlchemy async) для асинхронного доступа.

### Обоснование TimescaleDB для events

- Events — append-only, основной объём данных.
- Запросы по временным диапазонам (`WHERE ts BETWEEN ... AND ...`) — основной паттерн.
- Automatic chunk management, compression.
- Совместим с обычным PostgreSQL (те же инструменты, тот же SQL).

---

## R-009: Валидация команд (Principle VI)

### Решение

Перед отправкой команды в MQTT, сервис валидирует:

1. `house_id` существует и `is_active=true`.
2. `ga` существует в таблице objects для данного дома.
3. `value` соответствует `datatype` объекта:
   - datatype 1/1001 (bool): value ∈ {true, false, 0, 1}
   - datatype 5/5001 (percent): 0 ≤ value ≤ 100
   - datatype 7 (uint16): 0 ≤ value ≤ 65535
   - datatype 8 (int16): -32768 ≤ value ≤ 32767
   - datatype 9/9001 (float16): проверка на число
   - datatype 14 (float32): проверка на число
   - datatype 255 (string): проверка на строку
4. Объект имеет тег `control` (предупреждение, если записывается в `status`-объект).

---

## R-010: Аудит безопасности и live-hardening (2026-07)

### Контекст

Аудит облачной части + security-review: MQTT без ACL, дефолт `auth_required=False`, слабая валидация команд, открытые docs, просроченная копия cert у mosquitto.

### Решение (внедрено)

- **MQTT ACL** на elion: пользователь контроллера `lm_estate` ограничен `cm/house/#`; localhost:1883 для сервера без изменений.
- **Auth**: в `ENV=production` auth обязателен (fail-fast); write-scope на mutating REST/MCP; валидация value/batch в `command_validation.py`; MCP rate-limit fail-closed; docs off в prod.
- **Образ**: `cottage-monitoring:0.2.4` (локальный build → docker load на elion).
- **Cert mosquitto**: sync из Let's Encrypt через deploy-hook + short-chain для совместимости с LM (детали в 002 R-013).

### Альтернативы / отложено

Секреты: не светить в git — **R-012** (домашний уровень).

---

## R-011: operation_traces и E2E-тест MCP-команд (2026-07)

### Контекст

Нужна наблюдаемость цепочки «бот/MCP → сервер → MQTT → LM → ack» и воспроизводимый живой тест (включить холл → 30 с → выключить).

### Решение

- Таблица **`operation_traces`**: `kind` ∈ {`mcp_tool`, `command_sent`, `command_ack`}, `ref` = имя tool или `request_id`, `duration_ms`, `status`, `details` (JSON).
- **`trace_persist`**: по умолчанию `true` при `ENV=dev`, `false` в production (см. `config.py`).
- **RTT** в `commands`: `ts_ack - ts_sent`; дублируется в `command_ack.duration_ms`.
- **Живой тест на LM**: dev MCP (`:8322`) + временно пустой `MQTT_TOPIC_PREFIX` (см. quickstart). LM в prod слушает `cm/...`, не `dev/cm/...`.
- **MCP tools**: для физики предпочтительно `set_commands` с GA; `set_light` требует `objects` в БД инстанса.
- Временные API keys: `cottage-create-api-key` → revoke после теста.

### Проверка (2026-07-16)

`set_commands` `1/1/15` true → ack `applied:true`; через 30 с false → ack `applied:true`; traces: mcp_tool → command_sent → command_ack (ok); RTT ON ~2.5 s, OFF ~0.5 s.

---

## R-013: X-Cottage-Dry-Run — полный MCP-путь без MQTT (2026-07)

### Контекст

Бенч агентов (Hermes/OpenClaw + Caila) должен прогонять resolve + MCP write tools на prod-схеме объектов, но **не слать команды в шину**.

### Решение

- Заголовок `X-Cottage-Dry-Run: 1|true|yes|on` (middleware → contextvar).
- `send_command(..., dry_run=True)` пишет `commands.status=dry_run`, `payload.dry_run=true`, **skip MQTT publish**.
- Retry scheduler смотрит только `status=sent` — dry_run не ретраится.
- Бенч: `server/scripts/bench_mcp_models/` + mcporter alias `cottage-dry` с этим header; `--e2e` отказывается работать с `cottage`/`cottage-dev` без dry-run.

### Альтернативы

- Отдельный mock MQTT — лишняя инфра.
- Только model-only bench — не меряет MCP/resolve latency.

---

## R-012: Секреты — уровень «частный дом» (не светить случайно)

### Контекст

Это домашняя установка, не enterprise. Цель — **не закоммитить пароли в git и не кидать их в чат/скрин**, а не регулярная ротация и разделение ролей.

### Достаточно

1. В `specs/**` / README — плейсхолдеры; живые пароли LM — в **локальном** `secrets/lm.env` (gitignore), шаблон `secrets/lm.env.example`.
2. Скрипты читают файл сами: `./deploy/deploy-lftp.sh`, `./deploy/lm-apps.sh stop|start|health` — пароль в голове не нужен.
3. На elion — `/etc/cottage-monitoring/*.env` и OpenClaw secrets как сейчас.
4. Не коммитить `.env` / `secrets/lm.env` с реальными значениями; в чатах/скринах — не светить.

### Не требуется (осознанно отложено)

- Плановая ротация LM / MQTT / DB / API keys.
- Отдельные PG-роли, age/gpg-бэкапы секретов, pre-commit-сканеры, runbook «ротация за 30 минут».
- Смена паролей «потому что когда-то светились в git» — только если реально утек публичный репо или пароль ушёл чужим.

### Критерий

В tracked-файлах нет рабочих паролей. Живые LM-пароли — в gitignored `secrets/lm.env`; скрипты деплоя его читают.

---

## R-014: Модели агента для Cottage MCP — Flash + изолированный контекст (2026-07)

### Контекст

OpenClaw `main` на `gpt-5.6-sol` даёт ощущение ответа ~1 мин на бытовые команды («выключи свет», «отчёт по дому»). Нужно понять: узкое место — MCP/MQTT или LLM-петля; какая модель достаточна; можно ли ускорить отдельным агентом.

### Метод измерения

Скрипт `server/scripts/bench_mcp_models/` на elion (`~openclaw/.openclaw/workspace/cottage-mcp-bench/`):

| Режим | Что меряет | MQTT |
|-------|------------|------|
| model-only | 1× LLM → выбор tool | нет |
| `--e2e` + alias `cottage-dry` | полный agent loop (LLM → MCP → LLM…) | **нет** (`X-Cottage-Dry-Run`, R-013) |

Сценарии e2e: свет 1 этаж / setpoint 15°C кухня / отчёт по дому. Провайдер моделей: **Caila**.

Метрики e2e:

- `ms_to_command` — wall до возврата write-tool (`status=dry_run` ≈ момент, когда ушёл бы MQTT publish)
- `ms_to_final_text` — wall до финального текста пользователю (после 2–3 turns)
- MCP tool latency отдельно (~0.8–1.1 s на read/write resolve)

### Результаты (elion, 2026-07-17)

**E2E avg wall (короткий system prompt, без OpenClaw memory):**

| Модель | avg wall | notes |
|--------|---------:|-------|
| gemini-3.5-flash | **~5.6 s** | лучший баланс скорость/качество tools |
| minimax-m2.7 / glm-5.1 / haiku-4.5 / gpt-5.4-mini | ~6–8 s | близко |
| gpt-5.6-sol / claude-sonnet-4.6 | **~11 s** | ~2× медленнее Flash на том же промпте |

**Детализация gpt-5.6-sol (повторный прогон `sol_detail.json`):**

| Команда | ms_to_command (≈ MQTT) | ms_to_final_text | turns |
|---------|-----------------------:|-----------------:|------:|
| свет 1 этаж | ~24 s | ~54 s | 3 (set_lights → get_command_status → текст) |
| 15°C кухня | ~15 s | ~23 s | 2 |
| отчёт по дому | — (нет write) | ~14 s | 2 (4 read tools → текст) |

**Живой OpenClaw `main`:** в trajectory видны `cacheRead` **34k–200k** токенов на ход; wall на sol в топиках может быть минуты. Это не MCP (~1 s), а контекст + reasoning + несколько LLM turns.

Качество tool selection на Flash/Haiku/Mini для cottage-команд в бенче **не хуже** Sonnet/Sol (все pass на e2e сценариях). Reasoning для dial-команд не нужен.

### Решение (рекомендация)

1. **Отдельный OpenClaw-агент `cottage`** (или isolated sub-agent):
   - model: `gemini-3.5-flash` (Caila / OpenRouter) — default
   - fallback: `claude-haiku-4.5` или `gpt-5.4-mini`
   - workspace: только skill `cottage-monitoring` + короткий AGENTS.md (без SOUL/MEMORY/heartbeat main)
   - MCP: `cottage` loopback; для бенчей — `cottage-dry`
2. **`main`** оставить на sol/sonnet для общего диалога и памяти.
3. Роутинг: Telegram-топик / peer binding → `cottage`, либо `sessions_spawn` с `context: "isolated"` и model Flash.
4. **Hermes:** MCP + смена `/model` ок, но нет multi-agent isolation как у OpenClaw — для «дом-агент с минимальным контекстом» предпочтителен OpenClaw.

### Оценка ускорения («в 2 раза?»)

| Сравнение | Ожидаемый выигрыш |
|-----------|-------------------|
| Только смена модели sol → Flash при **том же** коротком контексте (наш e2e) | **≈ 2×** быстрее wall (11 s → 5–6 s) |
| Отдельный агент Flash + **минимальный** контекст vs текущий OpenClaw main (sol + 30–200k cache) | **существенно больше 2×** (часто 5–10× на write/отчёте); «×2» — консервативная нижняя граница |
| MCP/resolve | почти не меняется (~1 s); выигрыш почти целиком в LLM turns |

Итого: формулировка «примерно в 2 раза быстрее» **корректна как минимум** для model-swap на одинаковом промпте; при выносе в изолированного Flash-агента реальное ускорение ответа пользователю обычно **не меньше 2× и часто заметно выше**.

### Артефакты

- Код бенча: `server/scripts/bench_mcp_models/`
- Live копия: `~openclaw/.openclaw/workspace/cottage-mcp-bench/results/{e2e,sol_detail,latest}.json`
- Dry-run: R-013 / image `0.2.6`
- Инструкция для OpenClaw (setup + примеры + канон AGENTS.md): `specs/001-server-mqtt-ingestor/openclaw-cottage-agent-instructions.md`
- Skill routing ladder (чайник / discover / без `mcporter list`): `skills/cottage-monitoring/SKILL.md`

### Live verify (2026-07-17, топик «Усадьба»)

Агент `cottage` на Flash: свет по этажам / торшер+подсветка; `set_kettle` / `get_kettle` (температура); `get_energy_status` по фазам — ок. Routing ladder в `AGENTS.md` персистентен (не повторять в каждой сессии). Session history в топике сохраняет follow-up («подтверждаю», «он был включен»).

---

## R-016: OpenClaw native MCP вместо exec/mcporter (2026-08)

### Контекст

Агент `cottage` ходил в дом через `exec` + `mcporter`. Модель иногда вызывала несуществующее `mcporter list-commands cottage` → exit 1 → баннер `⚠️ Exec failed` в Telegram (даже когда skill запрещал list).

### Решение

1. `mcp.servers.cottage` в `openclaw.json` (streamable-http → `127.0.0.1:8321/mcp`, `Authorization: Bearer ${COTTAGE_API_KEY}`).
2. `toolFilter.exclude`: `resources_*`, `prompts_*`.
3. Agent `cottage`: `tools.profile=minimal`, `alsoAllow: ["bundle-mcp"]` — **без** `exec`.
4. Agent `main`: `tools.deny: ["bundle-mcp"]` — house tools не светятся в общем чате.
5. mcporter остаётся для benches / `cottage-dry` / shell debug.
6. `TOOLS.md` в workspace-cottage **не** учить `mcporter call` как путь агента. Канон: `openclaw-cottage-tools.md`. Live 2026-08-29: файл переписан под `cottage__*`; issue #4.
7. `mcporter generate-cli` / CLI-снимок сервера — не путь агента `cottage` (17 tools, `minimal`+`bundle-mcp`). Канон остаётся Nord MCP; mcporter — шелл и бенчи. 2026-08-29.

### Verify (2026-08-10)

- `openclaw mcp probe cottage` → 15 tools.
- Smoke: `cottage__get_house_status`; follow-up «детальнее» → `cottage__get_energy_status` + `cottage__get_temperature`, без exec.

### Артефакты

- `skills/cottage-monitoring/references/openclaw-connection.md`
- `specs/001-server-mqtt-ingestor/openclaw-cottage-agent-instructions.md`
- `specs/001-server-mqtt-ingestor/openclaw-cottage-tools.md`

---

## R-017: `set_lights` skip_unchanged должен смотреть status, не control (2026-08-15)

### Контекст

Telegram: «выключи свет на втором этаже». Агент вызвал `set_lights query=«2 этаж» on=false`. Ответ: выключен холл, остальные зоны уже были выключены. Физически остались гореть Настя, Тим, кабинет, ванна 2 этаж.

Команда `f09b8339-da9a-4c08-8214-294f6a0dd61a` (19:13:15Z, status=ok) отправила **один** GA: `1/1/15` (холл 2 этаж). `skip_unchanged` сравнивал `current_state` **control** `1/1/*`. Выключатели на стене пишут в **status** `1/2/*`; control часто остаётся `false`. R-001 уже фиксирует: control «не обязательно отражает реальное состояние».

Дополнительно: status-объекты **без** тега `2floor` (только `light,status`). Резолв status с query «2 этаж» находит лишь имена с «2 этаж» в названии (холл, ванна) — Настя/Тим/кабинет не матчятся. Карту feedback надо строить по **всем** light status, парить по имени с control.

### Решение

`set_lights` / `list_lights`: on/off для skip и отображения = status `1/2/*` (имя `«Свет - … :status»`), fallback на control если status нет. Пишем по-прежнему в control `1/1/*`.

Та же дыра в **`set_commands`** (`skip_unchanged` сравнивал GA записи = control) и в **`get_kettle`**: поле `on` бралось из cmd `33/1/39`, не из state `33/1/38`. Live 2026-08-16: cmd=`true`, state=`false` (чайник выключен, агент мог сказать «уже включён»). `set_kettle` skip не делает — пишет всегда. `set_climate` / REST `/commands` / `set_light` skip не используют. `get_climate.relay_on` уже status `1/5/*`.

Дополнение: `set_commands` skip смотрит sibling (`:status` / `_state` / KNX mid+1); `get_kettle.on` = state, fallback cmd.

### Verify

Live 2026-08-15: control всех 2floor = false; status ON: `1/2/12` Настя, `1/2/13` Тим, `1/2/14` кабинет, `1/2/16` ванна.

---

## R-018: Principal grants — `house_ids` + `authorize` (2026-08-27)

### Контекст

`ApiKeyContext` держал один `house_id: str`. Nord Ops требует гранты на несколько домов в контексте, без junction-таблицы в этой итерации.

### Решение

- Контекст: `house_ids: frozenset[str]`; `default_house_id() -> str | None` (ровно один грант → id, иначе `None`).
- БД без изменений: `api_keys.house_id` одна колонка; при аутентификации `house_ids=frozenset({row.house_id})`.
- `authorize(ctx, house_id, permission)` — единственная проверка «дом ∈ house_ids» и scope; 403 с прежними формулировками.
- Middleware `/api/v1/houses/{id}` зовёт `authorize(..., "read")`. Write по-прежнему `require_write_scope` на mutating endpoints.
- MCP tools пока берут `ctx.default_house_id()` (один дом на ключ). Резолв optional `house_id` — отдельная задача Ops.

### Отклонено

- Таблица `api_key_houses` — не в этой итерации.

---

## R-019: GET /houses only grants + handler `list_houses` (2026-08-27)

### Контекст

`GET /api/v1/houses` отдавал все ряды `houses`. Middleware режет только путь `/houses/{id}`; список домов был утечкой грантов.

### Решение

- Handler `ops.houses.list_houses(session, *, house_ids: frozenset[str] | None) -> {items, total}`: `None` (auth off) — все дома; frozenset — `House.house_id IN house_ids`.
- REST `GET /houses` только берёт ctx (или None) и зовёт тот же handler. MCP `list_houses` и реестр Ops — отдельные задачи.
- Shape ответа без изменений (`HouseRead` items + `total`).

### Отклонено

- Отдельный `POST /ops/list_houses`.
- Регистрация MCP tool в этой задаче.

---

## R-020: Реестр Ops, диспетчер и резолв дома (2026-08-27)

### Контекст

Семантика жила только в MCP-обёртках: house_id прятался в ключе, write rate-limit срабатывал лишь на MCP-грани, а REST-грани Ops не было. Нужен один каталог операций на обе грани.

### Решение

- `ops/spec.py`: `OpSpec(name, permission, house_scoped, description, handler, params_model)` (frozen dataclass). `name` = имя MCP tool = сегмент URL.
- `ops/registry.py`: `OpsRegistry.register/get/names/all`; повторное имя — `ValueError`, неизвестное имя в `get` — HTTP 404. Модульный синглтон `registry`.
- `ops/resolve_house.py`: `resolve_house_id(ctx, house_scoped, requested)` — только членство в грантах. Не house-scoped → `None`; 0 грантов → 403; чужой дом → 403; один грант без аргумента → он же; >1 без аргумента → 400 `"house_id required"` (первый дом не выбираем).
- `ops/dispatch.py`: `dispatch(ctx, spec, *, house_id, params, session)` — `require_scope(permission)` → резолв дома → `authorize(ctx, house, permission)` → для write `agent_actions.check_write_rate_limit(ctx)` → handler. House-scoped: `handler(session, house_id, **params)`; non-scoped: `handler(session, house_ids=ctx.house_ids, **params)`, то есть `list_houses` фильтрует по грантам сам, а не по MQTT house_id.
- Rate-limit остаётся и в MCP-обёртках, пока они не переведены на реестр (следующая задача); двойного лимита нет, так как грань зовёт либо диспетчер, либо старую обёртку.

### Отклонено

- Валидация `params` по `params_model` внутри диспетчера — схему проверяет грань (FastAPI body / MCP tool schema); диспетчер не дублирует.
- Поддержка `ctx=None` (AUTH_REQUIRED=false) в диспетчере — решается на грани, когда появятся REST/MCP биндинги.

---

## R-022: `commands.actor_key_id` — актор команды (2026-08-27)

### Контекст

Nord Ops требует аудит «кто отправил команду». Комментарий в payload (`mcp set_lights …`) ненадёжен: его можно опустить или подделать. Нужна колонка в `commands`, которую пишет единственная точка постановки команды.

### Решение

- `commands.actor_key_id UUID NULL`, FK `api_keys.id` (alembic `008`).
- `send_command` читает `get_current_api_key_context()`: если ctx есть — `actor_key_id = ctx.key_id`; если нет (dry-run без ключа, ingest, `AUTH_REQUIRED=false`) — NULL.
- REST `POST /commands` и write-Ops не пишут колонку сами: все пути идут через `command_service.send_command`.
- `CommandRead` / грани REST и MCP не меняются: колонка — источник истины в БД, не в ответе API.

### Отклонено

- Писать `actor_key_id` в диспетчере Ops или в `POST /commands` — дублирует и пропускает другие входы в `send_command`.
- Обязательная колонка — ломает dry-run и пути без ключа.

---

## R-023: OpenClaw skill + `cottage-ops catalog` (2026-08-28)

### Контекст

Реестр и две грани уже есть (R-020, R-021): 16 Ops, MCP tools генерируются из каталога, REST `GET /ops` / `POST .../ops/{name}`. Telegram-агент `cottage` эти HTTP-грани не читает — он видит `SKILL.md` и `AGENTS.md`. Без `list_houses` / правил `house_id` в промпте Flash угадывает дом или зовёт CLI. Оператору нужна сверка имён без MCP-сессии и без открытия skill.

### Решение

- `SKILL.md` и канон `AGENTS.md` — короткий routing ladder + `list_houses` / `house_id` (дублировать в обоих: Flash может увидеть только одно). JSON-схемы Ops в промпт не копировать (`tools/list` уже отдаёт их). `bootstrapMaxChars` cottage = 5000, не раздувать.
- Telegram остаётся на MCP (`cottage__*`). REST `POST /ops` агенту не учить. CLI агенту не давать (`exec` запрещён).
- Операторский `cottage-ops catalog` / `catalog --json`: `load_catalog()` и те же имена, что реестр. Entry point в образе рядом с `cottage-create-api-key`.
- Выкладка skill на elion **после** образа с 16 tools: `openclaw skills install … --agent cottage --force` (или копия в `workspace/skills/cottage-monitoring/`; cottage workspace — симлинк). Затем канон в `workspace-cottage/AGENTS.md`, `openclaw mcp probe cottage` — 16 tools, старый чат `/new`.

### Отклонено

- JSON-схемы Ops в skill/AGENTS.
- REST `POST /ops` в промпте Telegram-агента.
- `cottage-ops` в `alsoAllow` агента cottage.
- rsync как единственный путь выкладки skill.

---

## R-024: Placement + `set_auto_heating` + kettle setpoint (2026-08-28)

### Контекст

Семейная витрина HA (R-025) должна рисовать этажи/комнаты и чайник без парсинга имён в компоненте. Telegram и HA ходят в один каталог Ops. На момент 0.2.9 каталог был 16 имён; авто ТП читалось из `get_climate`, писать `1/7/1` мог только `set_commands`. Чайник Redmond RK-M173S умеет нагрев до N °C, но Nord писал только bool в cmd `33/1/39`. Число в cmd ломает BLE.

### Решение

**Placement.** Поля `area` / `floor` на уже существующих read-Ops (лишние ключи JSON; MCP/Telegram не ломаются). Канон в `services/placement.py`: `floor` ∈ {`1`,`2`,`outside`} из тегов `1floor`/`floor1`, `2floor`/`floor2`, `outside`; `area` — русская комната как в KNX-именах (`кухня`, `гостиная`, `Настина комната`, …). Синонимы резолвера (`зал`→гостиная, `Настя`→Настина). Zigbee `zb_sensor_fl1_living_room_*` мапится **в Nord**, не в HA. Где поля: `list_lights.items[]`, `get_climate.zones[]`, `get_temperature.items[]`, `get_sensors.items[]`; `get_kettle` ставит `area` только если резолвер классифицировал (иначе ключ не ставим). Новых имён Ops нет. `get_sensors(kind="humidity"|"battery")` резолвит `DiscoverKind.SENSOR` + `ROOM_HUMIDITY` / `ROOM_BATTERY` (не `DiscoverKind("battery")`); `zb_sensor` + `battery` (или имя `*_battery`) классифицируется как `ROOM_BATTERY` до generic SENSOR.

**`set_auto_heating`.** Новый write-Op → GA `1/7/1` (`on: bool`). Выкл = Lua гасит все реле ТП. Не путать с реле зоны (`1/5/*`). Read по-прежнему `get_climate.auto_heating_enabled`; отдельный `get_auto_heating` не заводим. Каталог: **17** имён.

**Чайник setpoint.** `SetKettleParams`: `on` и/или `setpoint_c` (40–100 включительно). Каталог не расширяется новым Op name.

- `set_kettle(setpoint_c=…)` пишет объект с `setpoint` в имени или тегах. **Никогда** не пишет °C в `33/1/39`.
- Нет объекта уставки → HTTP 404 `Kettle setpoint object not found`. `get_kettle` всегда отдаёт ключ `appliance.setpoint_c` (`None`, пока объекта нет).
- Классификация setpoint в `_group_appliances` **до** ветки temp.
- Cmd-матчи в `set_kettle` пропускают объекты setpoint (имя/тег), чтобы уставка с тегами `control`+`zigbee_send` не считалась cmd. Если `on` и `setpoint_c` заданы вместе и cmd ambiguous/404 **после** успешной записи уставки — ответ всё равно содержит ключ `setpoint` (результат не теряется).

**Объект на LM (эта волна, не follow-up).** Live-инвентарь: только `33/1/37` temp, `33/1/38` state, `33/1/39` cmd (bool). Объекта уставки нет. Завести на LogicMachine: имя `ble_teapot_RK-M173S_setpoint`, теги `ble,teapot,setpoint`, datatype float °C, writable; resident не должен слать число в `33/1/39`. Пока объекта нет — `appliance.setpoint_c` = `None`, HA `water_heater` без слайдера уставки (только on/off + текущая T).

### Отклонено

- Новый Op `set_kettle_setpoint` / `get_auto_heating`.
- Запись температуры в cmd GA `33/1/39`.
- Таблица комнат в YAML HA-компонента; маппинг Zigbee-имён в HA.

---

## R-025: HA Container на REST-грани (2026-08-28)

### Контекст

Семье нужен облачный GUI по этажам и комнатам. Grafana — SELECT-наблюдатель; Telegram — агент. HA не должен стать мозгом дома и не должен видеть KNX / MQTT `cm/#`.

### Решение

- Официальный **Container** `ghcr.io/home-assistant/home-assistant:stable` (не HA OS, без Supervisor/аддонов). systemd: `server/deploy/home-assistant.service`, `--network host`, volume `/var/lib/homeassistant:/config`.
- Listen `127.0.0.1:8123` (HA 2026.8+: Settings → System → Network; YAML `http:` после миграции игнорируется — не держать в `configuration.yaml`). Снаружи nginx `ha.black-castle.ru` + TLS + WebSocket. На elion публичный **443** — `stream ssl_preread` → `127.0.0.1:8443` (как grafana/elion); vhost HA слушает **8443**, не `0.0.0.0:443`. ACME: `certbot certonly --webroot`, не `certbot --nginx`. Проверка: `ss -lntp | grep 8123` → **127.0.0.1:8123**, не `0.0.0.0`.
- Custom component из `ha/custom_components/cottage_monitoring/` → volume скриптом `server/deploy/ha-sync-component.sh` (tar, не `git clone` продукта). Poll 30 с: `get_house_status`, `list_lights`, `get_climate`, `get_temperature`, `get_sensors` (humidity; Nord уже принимает `kind=battery` для Zigbee room batteries), `get_kettle`. Команды — `POST /api/v1/houses/{id}/ops/{name}`.
- Ключ Nord: `cottage-create-api-key --house house --name home-assistant --scopes read,write`. Секрет в `/var/lib/homeassistant/secrets.yaml` (`nord_ha_api_key`), не в git. Семья — встроенные users HA (логин на человека); в Nord все клики — один `actor_key_id`. `/mcp` на `ha.black-castle.ru` не открывать.
- Нет интеграций KNX/MQTT, нет подписки на `cm/#` / `ha/#`, `automations.yaml` пустой. Grafana по-прежнему SELECT-only.

Порядок выкладки: живой Nord 0.3.0 (alembic 008 **до** restart, probe 17) → ключ + smoke REST → HA. Пока GET `/ops` не отдаёт 17 имён и `list_lights` без `area`/`floor` — контейнер HA не стартовать.

**Live 2026-08-28:** Nord `cottage-monitoring:0.3.4` на elion (после energy/batteries wave). `pymorphy3` уже в образе. HA `https://ha.black-castle.ru`. HTTP YAML (`server_host`/`trusted_proxies`) импортирован в UI; блок `http:` из `configuration.yaml` убран. Overview favorites: `binary_sensor.dom_onlain`, `switch.avtoupravlenie_polami` (`frontend.system_data` key `home`, `hide_suggested_entities`). Чайник: вкл/выкл + текущая T; слайдер уставки и HA People отложены оператором. Спека HA-Nord: **Implemented**. go2rtc из `default_config` хардкодит `webrtc.listen: ":18555/tcp"`; на host-network это публичный bind. Entrypoint `go2rtc-localhost-entrypoint.sh` меняет на `127.0.0.1:18555` до `/init`. Остаток: YAML-платформы без config entry (warning 2027.8); recorder погоды когда-то писал °C на ветер/влажность.

### R-026: control/status не перепутаны; HA не должен poll'ить сразу после write (2026-08-28)

Live `list_lights`: все `ga` = `1/1/*` (control), `on` с status `1/2/*` по имени (`Свет - … :status`). `set_lights` пишет только control. Реле ТП: write `1/4/*`, read `1/5/*`; чайник: write `33/1/39` cmd, read `33/1/38` state.

Цикл вкл/выкл в HA: после команды компонент сразу делал 6 Ops. Status на шине отстаёт на ~0.5–3 с, poll видит старый off, UI откатывается, повторный клик (для zigbee/BLE — повторная запись True) даёт выключение. Фикс: optimistic state + refresh через 2.5 с.

Пустая area «спальня»: `zb_sensor_fl2_bedroom_*` в LM — датчик **гостевой** (`manage_warm_floor.lua`), не спальни 1 этажа. Placement отдавал `area=спальня` на 2 этаже → HA квалифицировал «спальня (1 этаж)» / «спальня (2 этаж)», канон «спальня» оставался пустым. Также `tima_bedroom` / `nastya_bedroom` и KNX «Тимина» (одна «н»).

### Отклонено

- YAML REST sensors/кнопки; MQTT Discovery; HA OS / Supervisor.
- Bridge + `host.docker.internal:8321` как основной путь HA→Nord (Nord слушает `-p 127.0.0.1:8321`).
- Users / OAuth в Nord; публичная витрина на `monitoring-dev`.

### R-027: HA energy snapshot (6 GA), батареи, Grafana iframe (2026-08-28)

HA coordinator добавляет два read: `get_energy_status` и `get_sensors` `kind=battery`. Poll — **8** вызовов: `get_house_status`, `list_lights`, `get_climate`, `get_temperature`, `get_sensors` humidity, `get_sensors` battery, `get_energy_status`, `get_kettle`. Каталог Ops остаётся **17** имён (новых Ops нет).

Шесть чисел в HA — allowlist GA в snapshot компонента, не сужение Nord `ENERGY_SUMMARY_GAS` (Telegram и Grafana SQL по-прежнему видят фазы, Q/S, `32/1/39`). Счётчик ЖКХ в HA — `32/1/59` (consumption Total), не `32/1/39`. Hour/daily: `state_class=total`; meter (`unique_id` `house:energy:meter`): `state_class=total_increasing`. Шаблон Energy: `server/deploy/ha/energy-grid.example.json`.

Lovelace YAML «Графики» (`cottage-graphs`) встраивает Grafana UID `cottage-energy` и `cottage-batteries`. На elion — только `allow_embedding = true` (`grafana-embedding.ini.snippet`). Если iframe пустой (cookie не шарится между `ha.` и `elion.`) — markdown-ссылка с логином. Анонимный Grafana **запрещён**.

**Live 2026-08-28 (Task 5):** Nord `0.3.4`; `GET /ops` = 17; battery dry-run 12; `get_energy_status` с `32/1/39`. HA entity_id Счётчик = **`sensor.schetchik`**, Сейчас = `sensor.seichas`; Energy grid `stat_energy_from=sensor.schetchik`. Шесть `house:energy:*` + 12 `house:sensor_battery:*`. Grafana embedding включён; iframe в Lovelace есть, но cookie cross-subdomain `ha.`→`elion.` может оставить рамку пустой — **рабочий путь для семьи: markdown-ссылки** в той же view. Спека energy/Grafana: **Implemented**.

Energy dashboard читает **часовую** `statistics.sum`, не live state. Сенсор заведён вечером 28.08 — без импорта август пустой. Backfill: `server/deploy/ha/import-meter-lts.py` (HA stop; hourly last `32/1/59` из Timescale; `sum = reading - baseline`; seed `statistics_short_term`, иначе recorder ставит новую нулевую точку на текущие ~67833 кВт·ч и график падает). Live: **661** часов, baseline ≈ 67333.8, last_sum ≈ **499.5** кВт·ч за август. Бэкап БД: `home-assistant_v2.db.bak-before-aug-lts`.

---

## R-026: MCP SDK 2.x / spec 2026-07-28 — не сейчас (2026-08-29)

### Контекст

GitHub issue #5: Python SDK 2.x говорит stateless MCP (без `initialize` / `Mcp-Session-Id`). У нас пин `mcp>=1.0,<2` после падения деплоя 0.2.7 (`mcp.server.fastmcp` исчез). Код: FastMCP + `session_manager.run()` в lifespan. Один контейнер Nord на loopback — sticky session не проблема. OpenClaw на elion **2026.7.1-2**, клиент ещё 2025-era; PR OpenClaw на 2026-07-28 открыт и с фолбэком на handshake 2025. v1.x SDK в maintenance (security-фиксы).

### Решение

Оставить `mcp>=1.0,<2`. Не апгрейдить Nord раньше клиента. Триггеры пересмотра: OpenClaw на elion говорит только 2026-07-28 без фолбэка; несколько реплик Nord за балансировщиком; CVE в mcp 1.x без патча на v1.

### Отклонено

- Апгрейд «чтобы соответствовать спеке» без боли на клиенте.
- CLI-снимок (`generate-cli`) вместо native MCP у агента `cottage`.

---

## R-015: Grafana — дашборды телеметрии и алерты (2026-07)

### Контекст

FR-045 оставлял Grafana-дашборды **метрик приложения** вне scope фичи. Параллельно на elion уже есть Grafana OSS; телеметрия дома лежит в PostgreSQL/Timescale (`events`, `current_state`). Нужна ops-визуализация и Telegram-алерты без отдельного Alert Engine в приложении.

Рост CPU на LM (loadavg, GA `34/1/6..8`) после compact daemon (см. **002 R-015**) потребовал отдельный дашборд и порог на load15.

### Решение

1. **Источник данных:** PostgreSQL datasource UID `cottage-monitoring-pg`, роль `cottage_grafana` (SELECT-only), БД `cottage_monitoring`.
2. **Дашборды (file provisioning):** генератор `server/deploy/grafana/generate_dashboards.py` → JSON в `/var/lib/grafana/dashboards/cottage`. Папка **Cottage**.
   - Overview, Electricity, Climate, Lights, Batteries, **LM Load** (`cottage-lm-load`).
3. **Деплой:** `./server/deploy/grafana/deploy.sh` (не править JSON вручную на сервере).
4. **Алерты:** Grafana Alerting → contact point `cottage-telegram`, route `team=cottage`.
   - `cottage-house-stale` — дом offline / stale >15m (critical, for 5m).
   - `cottage-lm-load15-high` — GA `34/1/8` > **2.0** for **10m** (warning); `noDataState=OK`.
   - Секреты: `/etc/cottage-monitoring/telegram.env`. Скрипт: `deploy_alerts.sh`.
5. **MCP:** service account token для Cursor (`grafana-mcp.token`); OSS → не Cloud Assistant.

### Lights instant (2026-08-16)

Таблицы «Свет» / «Свет сейчас» раньше брали **control** `1/1/*` (комментарий: «у status битый timestamp» — старый Lua `false→nil`, **002 R-014**). После фикса daemon status `1/2/*` достовернее (выключатель). История графиков уже была на `1/2/*`. Реле ТП в Overview/Climate — status `1/5/*` (без изменений).

Stat-плитки (`time_series` + колонка `metric`): Grafana Postgres long→wide требует сортировку по `time`. `ORDER BY metric` даёт **No data**. Instant-снимок для ТП (Stat) по-прежнему `now() AS time`.

Свет сейчас (2026-08-16, вечер): Stat не умеет PNG. Плитки света — **Canvas**: прямоугольник с `background.image.mode=field`, SQL (format `table`) отдаёт URL `light-on-128.png` / `light-off-128.png`. Иконки: `server/deploy/grafana/icons/` → `/usr/share/grafana/public/img/cottage/` (полный URL, иначе Grafana префиксует `build/`). Список комнат зашит (как история графиков) — Canvas не плодит элементы из строк запроса.

История света: не timeseries 0/1, а **state-timeline** (строб). Сырые `events` + снимок last-state на левой границе окна (`DISTINCT ON ga … ts < $__timeFrom()`), иначе полоса не знает состояние до первого события в диапазоне. Auto-refresh дашбордов Cottage: 30s, кроме Batteries/LM Load (1m).

### Отклонено / не смешивать

- Дашборды Prometheus `/metrics` приложения — по-прежнему вне FR-045 (отдельная итерация при необходимости).
- Alert Engine внутри FastAPI — не нужен при Grafana+Telegram.
- Писать loadavg в Prometheus с LM — избыточно: уже есть KNX GA → MQTT → `events`.

### Документация

- Ops: `specs/001-server-mqtt-ingestor/quickstart.md` § Grafana
- Deploy README: `server/deploy/grafana/README.md`
- LM CPU / batching: `specs/002-logicmachine-mqtt-client/research.md` **R-015**

---

## Сводка решений

| ID | Тема | Решение | Альтернатива |
|----|------|---------|-------------|
| R-001 | Классификация объектов | instant + timeseries маркировка в objects table | Единый pipeline без маркировки |
| R-002 | Кеш состояния | Redis HSET per house | In-memory dict, только PostgreSQL |
| R-003 | API фреймворк | FastAPI | aiohttp, Django, Flask |
| R-004 | Деплой | Docker + systemd; bridge + host-gateway | `--network=host` (отвергнуто после hardening) |
| R-005 | Логирование | structlog + RotatingFile + JSON | loguru, python-json-logger |
| R-006 | Nginx | Reverse proxy на порт 8321 | Порт 8080 (стандартный, может конфликтовать) |
| R-007 | MQTT клиент | aiomqtt (async) | paho-mqtt (sync) |
| R-008 | БД | PostgreSQL 16 + TimescaleDB | Только PostgreSQL |
| R-009 | Валидация команд | По datatype + tags из objects table | Без валидации |
| R-010 | Security hardening | ACL + auth defaults + 0.2.4 + cert hook | Открытый брокер / auth off |
| R-011 | MCP traces / E2E | `operation_traces`; RTT; dev prefix caveat | Только логи без БД |
| R-012 | Secrets | `secrets/lm.env` локально; не в git | Ротация / enterprise |
| R-013 | Dry-run MCP writes | `X-Cottage-Dry-Run` → status=dry_run, no MQTT | Mock broker / model-only |
| R-014 | Cottage agent model | OpenClaw agent `cottage` + gemini-3.5-flash, min context | sol на main / Hermes `/model` |
| R-015 | Grafana telemetria | PG dashboards + Telegram alerts (load15) | App Alert Engine / only Prometheus |
| R-016 | OpenClaw native MCP | `mcp.servers.cottage` + `bundle-mcp` (no exec) | mcporter via `exec` / list-commands |
| R-017 | set_lights skip | skip_unchanged по status `1/2/*`, не control `1/1/*` | force / skip_unchanged=false |
| R-018 | Principal grants | `house_ids` + `authorize`; DB column unchanged | junction `api_key_houses` |
| R-019 | GET /houses grants | `list_houses` handler; auth off → all, else IN house_ids | unfiltered list / POST /ops/list_houses |
| R-020 | Ops registry + dispatch | `OpSpec`/`OpsRegistry`, resolve house (>1 грант → 400), write rate-limit в диспетчере | params-валидация в диспетчере / выбор первого дома |
| R-021 | Каталог Ops → две грани | `catalog.load_catalog()` в lifespan; MCP tools генерируются из реестра; REST `GET /ops` + `POST .../ops/{name}` | ручные `@mcp.tool` рядом с реестром / регистрация по импорту |
| R-022 | Command actor | `commands.actor_key_id` nullable FK `api_keys.id`; пишет только `send_command` из ctx | колонка в диспетчере / обязательный FK |
| R-023 | Skill + catalog CLI | SKILL/AGENTS: `list_houses`+`house_id`; `cottage-ops catalog` = реестр; probe 16 tools (на момент заметки; с 0.3.0 — 17, R-024) | схемы Ops в промпте / REST POST в skill / CLI агенту |
| R-024 | Placement + авто ТП + kettle | `area`/`floor` на read-Ops; `set_auto_heating`→`1/7/1`; каталог 17; `set_kettle` on и/или setpoint_c 40–100, °C не в cmd; LM объект `ble_teapot_RK-M173S_setpoint` | новый Op setpoint / °C в cmd / маппинг комнат в HA |
| R-025 | HA Container | офиц. Container, host net, loopback 8123, nginx `ha.black-castle.ru`+WS, ключ `home-assistant`, component tar; нет KNX/MQTT/automation | YAML REST / MQTT discovery / HA OS |
| R-026 | MCP SDK 2.x | оставить `mcp>=1.0,<2` до боли на клиенте / реплик / CVE; native MCP агента, не generate-cli | апгрейд Nord первым / CLI как путь Telegram |
