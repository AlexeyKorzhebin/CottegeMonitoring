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
Контейнеры используют `--network=host` для доступа к PostgreSQL, Redis и Mosquitto на localhost.

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
  --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  -v /var/log/cottage-monitoring/prod:/var/log/cottage-monitoring \
  cottage-monitoring:latest
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
  --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.dev.env \
  -v /var/log/cottage-monitoring/dev:/var/log/cottage-monitoring \
  cottage-monitoring-dev:latest
ExecStop=/usr/bin/docker stop cottage-monitoring-dev
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### Сборка и деплой образов

```bash
cd /opt/cottage-monitoring/server
docker build -t cottage-monitoring:latest -f deploy/Dockerfile .

# Миграции (через одноразовый контейнер)
docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  cottage-monitoring:latest alembic upgrade head

docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.dev.env \
  cottage-monitoring:latest alembic upgrade head
```

### Обоснование

- Docker: единый артефакт для prod, dev и CI — одинаковая среда везде.
- Systemd: управление жизненным циклом контейнеров (restart, logging, boot).
- `--network=host`: контейнер напрямую использует host PostgreSQL/Redis/MQTT на localhost.
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

## Сводка решений

| ID | Тема | Решение | Альтернатива |
|----|------|---------|-------------|
| R-001 | Классификация объектов | instant + timeseries маркировка в objects table | Единый pipeline без маркировки |
| R-002 | Кеш состояния | Redis HSET per house | In-memory dict, только PostgreSQL |
| R-003 | API фреймворк | FastAPI | aiohttp, Django, Flask |
| R-004 | Деплой | Docker + systemd (оба) | Только Docker |
| R-005 | Логирование | structlog + RotatingFile + JSON | loguru, python-json-logger |
| R-006 | Nginx | Reverse proxy на порт 8321 | Порт 8080 (стандартный, может конфликтовать) |
| R-007 | MQTT клиент | aiomqtt (async) | paho-mqtt (sync) |
| R-008 | БД | PostgreSQL 16 + TimescaleDB | Только PostgreSQL |
| R-009 | Валидация команд | По datatype + tags из objects table | Без валидации |
