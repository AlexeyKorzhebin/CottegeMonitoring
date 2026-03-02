# REST API Contract v1

**Base URL**: `/api/v1`
**Port**: 8321 (behind nginx)
**Framework**: FastAPI (auto-generated OpenAPI at `/docs`)
**Auth**: Без аутентификации (MVP — сервис за nginx, доступ ограничен сетью).
API Key header `X-API-Key` или JWT Bearer — отдельная итерация.

---

## Common

### Error Response

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "human readable description",
    "details": {}
  }
}
```

Codes: `VALIDATION_ERROR`, `NOT_FOUND`, `FORBIDDEN`, `CONFLICT`, `INTERNAL`

### Pagination

Query params: `?limit=50&offset=0`

Response wrapper for list endpoints:
```json
{
  "items": [...],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

---

## Endpoints

### Houses

#### GET /api/v1/houses

Список всех домов.

Response 200:
```json
{
  "items": [
    {
      "house_id": "house-01",
      "created_at": "2026-01-15T10:00:00Z",
      "last_seen": "2026-03-01T12:00:00Z",
      "online_status": "online",
      "is_active": true,
      "object_count": 150,
      "current_schema_hash": "sha256:abc123"
    }
  ],
  "total": 2
}
```

#### GET /api/v1/houses/{house_id}

Детали дома.

Response 200:
```json
{
  "house_id": "house-01",
  "created_at": "2026-01-15T10:00:00Z",
  "last_seen": "2026-03-01T12:00:00Z",
  "online_status": "online",
  "is_active": true,
  "object_count": 150,
  "active_object_count": 148,
  "current_schema_hash": "sha256:abc123",
  "schema_versions_count": 5
}
```

Response 404: `NOT_FOUND`

#### PATCH /api/v1/houses/{house_id}

Обновление дома (деактивация/реактивация).

Request:
```json
{
  "is_active": false
}
```

Response 200: updated house object

---

### Devices

#### GET /api/v1/houses/{house_id}/devices

Список контроллеров дома.

Response 200:
```json
{
  "items": [
    {
      "house_id": "house-01",
      "device_id": "lm-main",
      "created_at": "2026-01-15T10:00:00Z",
      "last_seen": "2026-03-01T12:00:00Z",
      "online_status": "online",
      "is_active": true
    }
  ],
  "total": 2
}
```

#### GET /api/v1/houses/{house_id}/devices/{device_id}

Детали контроллера.

Response 200: single device object
Response 404: `NOT_FOUND`

#### PATCH /api/v1/houses/{house_id}/devices/{device_id}

Обновление контроллера (деактивация/реактивация).

Request:
```json
{
  "is_active": false
}
```

Response 200: updated device object

---

### Objects

#### GET /api/v1/houses/{house_id}/objects

Список объектов дома.

Query params:
- `?tag=light` — фильтр по тегу
- `?q=кухня` — поиск по имени
- `?is_active=true` — только активные
- `?is_timeseries=true` — только time-series объекты

Response 200:
```json
{
  "items": [
    {
      "house_id": "house-01",
      "ga": "1/1/1",
      "object_id": 2305,
      "name": "Свет - крыльцо",
      "datatype": 1001,
      "units": "",
      "tags": ["control", "light", "outside"],
      "comment": "",
      "schema_hash": "sha256:abc123",
      "is_active": true,
      "is_timeseries": false
    }
  ],
  "total": 150
}
```

#### GET /api/v1/houses/{house_id}/objects/{ga}

Детали объекта. `ga` в URL через дефис: `1-1-1` (т.к. `/` зарезервирован).

Response 200: single object

---

### State (Current)

#### GET /api/v1/houses/{house_id}/state

Текущее состояние всех объектов дома. Читается из Redis (fast path).

Query params:
- `?ga=1/1/1,1/1/2` — batch запрос
- `?tag=light` — фильтр по тегу объекта

Response 200:
```json
{
  "items": [
    {
      "house_id": "house-01",
      "ga": "1/1/1",
      "ts": "2026-03-01T12:00:00Z",
      "value": true,
      "datatype": 1001,
      "server_received_ts": "2026-03-01T12:00:01Z",
      "object_name": "Свет - крыльцо",
      "object_tags": ["control", "light", "outside"]
    }
  ],
  "total": 150
}
```

#### GET /api/v1/houses/{house_id}/state/{ga}

Текущее состояние одного объекта. `ga` через дефис: `1-1-1`.

Response 200: single state entry

---

### Events (History)

#### GET /api/v1/houses/{house_id}/events

История событий.

Query params (обязателен хотя бы один из `from`/`to`):
- `?from=2026-03-01T00:00:00Z`
- `?to=2026-03-01T23:59:59Z`
- `?ga=1/1/1` — фильтр по GA
- `?type=knx.groupwrite` — фильтр по типу
- `?limit=100&offset=0`

Response 200:
```json
{
  "items": [
    {
      "house_id": "house-01",
      "ts": "2026-03-01T12:00:00Z",
      "seq": 123456,
      "type": "knx.groupwrite",
      "ga": "1/1/1",
      "object_id": 2305,
      "name": "Свет - крыльцо",
      "datatype": 1001,
      "value": true,
      "server_received_ts": "2026-03-01T12:00:01Z"
    }
  ],
  "total": 5000,
  "limit": 100,
  "offset": 0
}
```

#### GET /api/v1/houses/{house_id}/events/timeseries

Агрегированные данные для графиков.

Query params:
- `?ga=1/3/2` (обязательный)
- `?from=2026-02-28T00:00:00Z` (обязательный)
- `?to=2026-03-01T00:00:00Z` (обязательный)
- `?interval=1h` (1m, 5m, 15m, 1h, 6h, 1d)
- `?agg=avg` (avg, min, max, last, sum, count)

Response 200:
```json
{
  "ga": "1/3/2",
  "object_name": "Темп - тамбур",
  "interval": "1h",
  "aggregation": "avg",
  "points": [
    {"ts": "2026-02-28T00:00:00Z", "value": 22.5},
    {"ts": "2026-02-28T01:00:00Z", "value": 22.3},
    {"ts": "2026-02-28T02:00:00Z", "value": 22.1}
  ]
}
```

---

### Schemas

#### GET /api/v1/houses/{house_id}/schemas

История версий схемы.

Response 200:
```json
{
  "items": [
    {
      "house_id": "house-01",
      "schema_hash": "sha256:abc123",
      "ts": "2026-03-01T10:00:00Z",
      "count": 150,
      "is_current": true
    }
  ]
}
```

#### GET /api/v1/houses/{house_id}/schemas/{schema_hash}

Конкретная версия схемы.

Response 200:
```json
{
  "house_id": "house-01",
  "schema_hash": "sha256:abc123",
  "ts": "2026-03-01T10:00:00Z",
  "count": 150,
  "objects": [...]
}
```

#### GET /api/v1/houses/{house_id}/schemas/diff

Diff между двумя версиями схемы.

Query params:
- `?from=sha256:old` (обязательный)
- `?to=sha256:new` (обязательный)

Response 200:
```json
{
  "from_hash": "sha256:old",
  "to_hash": "sha256:new",
  "added": [{"ga": "1/1/21", "name": "Новый свет"}],
  "removed": [{"ga": "1/1/5", "name": "Свет - терраса"}],
  "changed": [{"ga": "1/1/1", "field": "name", "old": "Свет", "new": "Свет крыльцо"}]
}
```

---

### Commands

#### POST /api/v1/houses/{house_id}/commands

Отправка команды.

Request (single):
```json
{
  "ga": "1/1/1",
  "value": true,
  "comment": "Включить свет на крыльце"
}
```

Request (batch):
```json
{
  "items": [
    {"ga": "1/1/1", "value": true},
    {"ga": "1/6/4", "value": 22.5}
  ],
  "comment": "Включить свет + установить температуру"
}
```

Response 201:
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "house_id": "house-01",
  "status": "sent",
  "ts_sent": "2026-03-01T12:00:00Z"
}
```

Response 400: `VALIDATION_ERROR` (неизвестный GA, неправильный тип значения, дом неактивен)

#### GET /api/v1/houses/{house_id}/commands

История команд.

Query params:
- `?from=...&to=...`
- `?status=sent|ok|error|timeout`
- `?limit=50&offset=0`

Response 200: paginated list of commands

#### GET /api/v1/houses/{house_id}/commands/{request_id}

Детали команды + ack results.

Response 200:
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "house_id": "house-01",
  "ts_sent": "2026-03-01T12:00:00Z",
  "ts_ack": "2026-03-01T12:00:02Z",
  "status": "ok",
  "payload": {"ga": "1/1/1", "value": true},
  "results": [{"ga": "1/1/1", "applied": true, "error": null}],
  "retry_count": 0
}
```

---

### RPC

#### POST /api/v1/houses/{house_id}/devices/{device_id}/rpc/meta

Запрос meta через RPC.

Response 202:
```json
{
  "request_id": "uuid",
  "status": "requested"
}
```

#### POST /api/v1/houses/{house_id}/devices/{device_id}/rpc/snapshot

Запрос snapshot через RPC.

Response 202:
```json
{
  "request_id": "uuid",
  "status": "requested"
}
```

---

### Diagnostics

#### GET /health

Response 200:
```json
{
  "status": "healthy",
  "mqtt_connected": true,
  "db_connected": true,
  "redis_connected": true,
  "uptime_seconds": 86400
}
```

#### GET /metrics

Prometheus text format. Метрики из spec (FR-044):
- `ingestor_messages_total{house_id, message_type}`
- `ingestor_lag_seconds{house_id}` (histogram)
- `ingestor_house_status{house_id}` (gauge: 1=online, 0=offline)
- `ingestor_command_latency_seconds{house_id}` (histogram)
- `ingestor_command_timeout_total{house_id}`
- `ingestor_schema_changes_total{house_id}`
- `ingestor_mqtt_reconnects_total`
