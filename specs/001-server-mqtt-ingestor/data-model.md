# Data Model: Server MQTT Ingestor

**Date**: 2026-03-01 | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

---

## Database Environments

**Сервер**: `elion.black-castle.ru` (SSH-алиас: `elion`, доступ `ssh elion`, sudo)

Все сервисы (PostgreSQL, Redis, Mosquitto) расположены на одном сервере.
Приложение работает на этом же сервере — подключение к БД и кешу через `localhost`.

Две раздельные базы данных с идентичной схемой:

| Database | Назначение | Redis DB | MQTT Topic Prefix |
|----------|-----------|----------|-------------------|
| `cottage_monitoring` | **Production** — боевые данные от реальных домов | `redis://localhost:6379/0` | *(пусто)* → `lm/<house_id>/v1/...` |
| `cottage_monitoring_dev` | **Dev/Staging** — разработка, тесты, отладка | `redis://localhost:6379/1` | `dev/` → `dev/lm/<house_id>/v1/...` |

Обе базы создаются на одном PostgreSQL-сервере (`localhost:5432` на elion). Схема (миграции Alembic)
применяется к каждой базе отдельно. Redis использует разные DB-номера для изоляции кеша.
MQTT-топики разделены префиксом: dev-инстанс подписывается на `dev/lm/+/v1/#`,
prod — на `lm/+/v1/#`. Контроллеры публикуют только в prod-топики.

### Локальная разработка (SSH tunnel)

Для доступа к PostgreSQL и Redis с dev-машины используется SSH-туннель:

```bash
# SSH tunnel: PostgreSQL (5432) + Redis (6379) + MQTT (1883)
ssh -L 5432:localhost:5432 -L 6379:localhost:6379 -L 1883:localhost:1883 elion -N
```

После этого `localhost:5432`, `localhost:6379`, `localhost:1883` на dev-машине
указывают на сервисы elion.

---

## Entity Relationship Diagram

```
┌───────────────────┐       ┌───────────────────────────┐
│      houses        │──1:N──│        objects             │
│                   │       │                           │
│ house_id (PK)     │       │ house_id + ga (PK)        │
│ created_at        │       │ object_id, name, datatype │
│ last_seen         │       │ units, tags, comment      │
│ online_status     │       │ schema_hash, is_active    │
│ is_active         │       │ is_timeseries             │
└───────────────────┘       └───────────────────────────┘
        │                           │
        │ 1:N                       │ 1:N (via house_id+ga)
        ▼                           ▼
┌───────────────────┐       ┌───────────────────────────┐
│  schema_versions   │       │     current_state         │
│                   │       │                           │
│ house_id +        │       │ house_id + ga (PK)        │
│ schema_hash (PK)  │       │ ts, value, datatype       │
│ ts, count         │       │ server_received_ts        │
│ raw_meta_json     │       └───────────────────────────┘
└───────────────────┘
        │                   ┌───────────────────────────┐
        │                   │       events              │
        │                   │   (TimescaleDB hypertable)│
        │                   │                           │
        │                   │ house_id, ts (partition)  │
        │                   │ seq, type, ga, id, name   │
        │                   │ datatype, value, raw_json │
        │                   │ server_received_ts        │
        │                   └───────────────────────────┘
        │
        │               ┌───────────────────────────────┐
        │               │         commands              │
        │               │                               │
        │               │ request_id (PK)               │
        │               │ house_id, ts_sent, payload    │
        │               │ ts_ack, status, results       │
        │               │ retry_count                   │
        │               └───────────────────────────────┘
```

---

## Tables

### 1. houses

Реестр домов/объектов мониторинга.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| house_id | VARCHAR(64) | PK | Уникальный ID дома (из MQTT namespace) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Время первого появления |
| last_seen | TIMESTAMPTZ | | Время последнего сообщения |
| online_status | VARCHAR(16) | NOT NULL, DEFAULT 'unknown' | `online` / `offline` / `unknown` |
| is_active | BOOLEAN | NOT NULL, DEFAULT true | Деактивирован ли дом оператором |

```sql
CREATE TABLE houses (
    house_id        VARCHAR(64) PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ,
    online_status   VARCHAR(16) NOT NULL DEFAULT 'unknown',
    is_active       BOOLEAN NOT NULL DEFAULT true
);
```

### 2. objects

Реестр KNX-объектов (GA). Обновляется при получении meta/objects.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| house_id | VARCHAR(64) | PK (composite), FK → houses | Дом |
| ga | VARCHAR(16) | PK (composite) | Group Address (e.g., "1/1/1") |
| object_id | INTEGER | | ID объекта на контроллере |
| name | VARCHAR(256) | | Название объекта |
| datatype | INTEGER | NOT NULL | KNX datatype (1001, 9001, 14, etc.) |
| units | VARCHAR(32) | DEFAULT '' | Единицы измерения |
| tags | TEXT | DEFAULT '' | Теги через запятую |
| comment | TEXT | DEFAULT '' | Комментарий |
| schema_hash | VARCHAR(128) | | SHA256 хеш схемы, в которой объект последний раз присутствовал |
| is_active | BOOLEAN | NOT NULL, DEFAULT true | false = объект отсутствует в текущей схеме |
| is_timeseries | BOOLEAN | NOT NULL, DEFAULT false | true = объект интересен для графиков |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Время последнего обновления записи |

```sql
CREATE TABLE objects (
    house_id        VARCHAR(64) NOT NULL REFERENCES houses(house_id),
    ga              VARCHAR(16) NOT NULL,
    object_id       INTEGER,
    name            VARCHAR(256),
    datatype        INTEGER NOT NULL,
    units           VARCHAR(32) DEFAULT '',
    tags            TEXT DEFAULT '',
    comment         TEXT DEFAULT '',
    schema_hash     VARCHAR(128),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    is_timeseries   BOOLEAN NOT NULL DEFAULT false,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (house_id, ga)
);

CREATE INDEX idx_objects_house_active ON objects(house_id, is_active);
CREATE INDEX idx_objects_tags ON objects USING gin(to_tsvector('simple', tags));
```

#### Правила определения is_timeseries

Объект маркируется `is_timeseries=true` если выполняется **любое** из условий:
- Тег содержит: `temp`, `meter`, `humidity`, `weather`, `wind`, `pressure_mm`
- Datatype ∈ {9, 9001, 14} (числовые float) **И** тег НЕ содержит `control`
- Единицы измерения ∈ {°C, kWh, kVARh, W, A, V, Hz, %, мм, м/с, VA, VAR}

### 3. current_state

Актуальный срез состояния (upsert при каждом state/ga/*).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| house_id | VARCHAR(64) | PK (composite), FK → houses | Дом |
| ga | VARCHAR(16) | PK (composite) | Group Address |
| ts | TIMESTAMPTZ | NOT NULL | Timestamp из payload |
| value | JSONB | NOT NULL | Значение (может быть bool, number, string) |
| datatype | INTEGER | NOT NULL | KNX datatype |
| server_received_ts | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Время получения сервером |

```sql
CREATE TABLE current_state (
    house_id            VARCHAR(64) NOT NULL REFERENCES houses(house_id),
    ga                  VARCHAR(16) NOT NULL,
    ts                  TIMESTAMPTZ NOT NULL,
    value               JSONB NOT NULL,
    datatype            INTEGER NOT NULL,
    server_received_ts  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (house_id, ga)
);
```

#### Redis Cache (mirror of current_state)

```
Key:   state:{house_id}          (Redis HASH)
Field: {ga}
Value: {"ts": 1730000000, "value": true, "datatype": 1001, "server_received_ts": 1730000001}
```

### 4. events (TimescaleDB hypertable)

Append-only журнал событий. Без дедупликации (append-only, QoS 1 дубликаты допустимы).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | | Auto-increment surrogate |
| house_id | VARCHAR(64) | NOT NULL | Дом |
| ts | TIMESTAMPTZ | NOT NULL | Timestamp из payload |
| seq | BIGINT | | Порядковый номер из LM |
| type | VARCHAR(32) | | knx.groupwrite, snapshot, command, state.refresh |
| ga | VARCHAR(16) | | Group Address |
| object_id | INTEGER | | ID объекта |
| name | VARCHAR(256) | | Название объекта |
| datatype | INTEGER | | KNX datatype |
| value | JSONB | | Значение |
| raw_json | JSONB | NOT NULL | Полный исходный JSON |
| server_received_ts | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Время получения сервером |

```sql
CREATE TABLE events (
    id                  BIGSERIAL,
    house_id            VARCHAR(64) NOT NULL,
    ts                  TIMESTAMPTZ NOT NULL,
    seq                 BIGINT,
    type                VARCHAR(32),
    ga                  VARCHAR(16),
    object_id           INTEGER,
    name                VARCHAR(256),
    datatype            INTEGER,
    value               JSONB,
    raw_json            JSONB NOT NULL,
    server_received_ts  TIMESTAMPTZ NOT NULL DEFAULT now()
);

SELECT create_hypertable('events', 'ts');

CREATE INDEX idx_events_house_ts ON events(house_id, ts DESC);
CREATE INDEX idx_events_house_ga_ts ON events(house_id, ga, ts DESC);
```

### 5. schema_versions

Реестр версий схемы объектов.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| house_id | VARCHAR(64) | PK (composite), FK → houses | Дом |
| schema_hash | VARCHAR(128) | PK (composite) | SHA256 хеш схемы |
| ts | TIMESTAMPTZ | NOT NULL | Время получения |
| count | INTEGER | NOT NULL | Количество объектов в схеме |
| raw_meta_json | JSONB | NOT NULL | Полный JSON meta/objects |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Время записи в БД |

```sql
CREATE TABLE schema_versions (
    house_id        VARCHAR(64) NOT NULL REFERENCES houses(house_id),
    schema_hash     VARCHAR(128) NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,
    count           INTEGER NOT NULL,
    raw_meta_json   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (house_id, schema_hash)
);
```

### 6. commands

Команды управления устройствами.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| request_id | UUID | PK | Уникальный ID команды |
| house_id | VARCHAR(64) | NOT NULL, FK → houses | Дом |
| ts_sent | TIMESTAMPTZ | NOT NULL | Время отправки |
| payload | JSONB | NOT NULL | Полный JSON cmd |
| ts_ack | TIMESTAMPTZ | | Время получения ack |
| status | VARCHAR(16) | NOT NULL, DEFAULT 'sent' | sent / ok / error / timeout |
| results | JSONB | | Результаты из ack |
| retry_count | INTEGER | NOT NULL, DEFAULT 0 | Счётчик повторных отправок |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Время создания записи |

```sql
CREATE TABLE commands (
    request_id      UUID PRIMARY KEY,
    house_id        VARCHAR(64) NOT NULL REFERENCES houses(house_id),
    ts_sent         TIMESTAMPTZ NOT NULL,
    payload         JSONB NOT NULL,
    ts_ack          TIMESTAMPTZ,
    status          VARCHAR(16) NOT NULL DEFAULT 'sent',
    results         JSONB,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_commands_house_ts ON commands(house_id, ts_sent DESC);
CREATE INDEX idx_commands_status ON commands(status) WHERE status = 'sent';
```

### 7. chunk_buffer (internal, не персистентная)

Временный буфер для сборки meta-чанков. Может быть in-memory (dict) или Redis.

```python
# In-memory structure
chunk_buffer: dict[str, dict] = {
    # key: f"{house_id}:{schema_hash}"
    "house-01:sha256:abc123": {
        "schema_hash": "sha256:abc123",
        "chunk_total": 3,
        "ts": 1730000000,
        "count": 189,
        "received": {1: [...], 2: [...], 3: [...]},  # chunk_no → objects
        "first_seen": datetime(...)
    }
}
```

---

## State Transitions

### House online_status

```
unknown ──[status=online]──→ online
online  ──[LWT offline]───→ offline
offline ──[status=online]──→ online
```

### Command status

```
         ┌──[retry < max]──┐
         ▼                 │
sent ──[ack ok]──→ ok     │
  │  ──[ack error]→ error  │
  │  ──[timeout]───→ sent ─┘ (retry)
  │  ──[timeout, retry exhausted]──→ timeout
  │
timeout ──[late ack ok]──→ ok (logged as late)
timeout ──[late ack error]→ error (logged as late)
```

---

## Validation Rules

### Command validation (Principle VI)

| Datatype | KNX Type | Allowed values | Python type |
|----------|----------|---------------|-------------|
| 1, 1001 | Boolean | true, false, 0, 1 | bool |
| 5, 5001 | Percentage | 0..100 (int) | int |
| 7 | Unsigned 16-bit | 0..65535 | int |
| 8 | Signed 16-bit | -32768..32767 | int |
| 9, 9001 | Float 16-bit | -671088.64..670760.96 | float |
| 14 | Float 32-bit | IEEE 754 float | float |
| 255 | String | any string | str |

### Object classification rules for is_timeseries

```python
TIMESERIES_TAGS = {"temp", "meter", "humidity", "weather", "wind", "pressure_mm"}
TIMESERIES_UNITS = {"°C", "kWh", "kVARh", "W", "A", "V", "Hz", "%", "мм", "м/с", "VA", "VAR"}
NUMERIC_DATATYPES = {9, 9001, 14}

def should_be_timeseries(obj: dict) -> bool:
    tags = set(t.strip() for t in obj.get("tags", "").split(","))
    if tags & TIMESERIES_TAGS:
        return True
    if obj.get("datatype") in NUMERIC_DATATYPES and "control" not in tags:
        return True
    if obj.get("units", "") in TIMESERIES_UNITS:
        return True
    return False
```
