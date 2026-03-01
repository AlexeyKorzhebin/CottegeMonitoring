# MQTT Topic Contracts v1

**Namespace**: `{prefix}lm/<house_id>/v1/` (где `{prefix}` — конфигурируемый `MQTT_TOPIC_PREFIX`)
**Broker**: Mosquitto на `elion.black-castle.ru` (localhost:1883 с сервера, SSH tunnel с dev-машины)
**Client ID**: `cottage-monitoring-server` (prod) / `cottage-monitoring-dev` (dev)

---

## Dev/Prod Topic Isolation

Для изоляции dev- и prod-потоков на одном MQTT-брокере используется конфигурируемый
префикс топиков `MQTT_TOPIC_PREFIX`:

| Окружение | `MQTT_TOPIC_PREFIX` | Wildcard подписка | Пример топика |
|-----------|--------------------|--------------------|---------------|
| **Production** | *(пусто)* | `lm/+/v1/#` | `lm/house-01/v1/events` |
| **Dev/Staging** | `dev/` | `dev/lm/+/v1/#` | `dev/lm/house-01/v1/events` |

Контроллеры LogicMachine публикуют **только** в prod-топики (`lm/<house_id>/v1/...`).
Dev-данные создаются тестовыми клиентами с префиксом `dev/`.

**MQTT Client ID** также различается по окружению для предотвращения конфликтов
сессий на одном брокере.

---

## Subscriptions (Server subscribes)

| Pattern | QoS | Retain | Purpose |
|---------|-----|--------|---------|
| `{prefix}lm/+/v1/events` | 0/1 | no | Журнал событий от домов |
| `{prefix}lm/+/v1/state/ga/+` | 1 | yes | Последнее состояние объектов |
| `{prefix}lm/+/v1/meta/objects` | 1 | yes | Полная схема объектов |
| `{prefix}lm/+/v1/meta/objects/chunk/+` | 1 | yes | Чанки схемы объектов |
| `{prefix}lm/+/v1/status/online` | 1 | yes | Online/offline (LWT) |
| `{prefix}lm/+/v1/cmd/ack/+` | 0/1 | no | Подтверждения команд |
| `{prefix}lm/+/v1/rpc/resp/+/+` | 0/1 | no | Ответы RPC |

Wildcard subscription: `{prefix}lm/+/v1/#`

## Publications (Server publishes)

| Topic | QoS | Retain | Purpose |
|-------|-----|--------|---------|
| `{prefix}lm/<house_id>/v1/cmd` | 1 | no | Команды управления |
| `{prefix}lm/<house_id>/v1/rpc/req/<client_id>` | 0/1 | no | RPC запросы |

---

## Topic Parsing

```
{prefix}lm/<house_id>/v1/<rest...>
```

Topic parser сначала отбрасывает `MQTT_TOPIC_PREFIX` (если задан), затем разбирает
оставшуюся часть по стандартной структуре `lm/<house_id>/v1/<rest>`.

| rest | Message Type | Handler |
|------|-------------|---------|
| `events` | EVENT | event_service.handle() |
| `state/ga/<ga>` | STATE | state_service.handle() |
| `meta/objects` | META_FULL | schema_service.handle_full() |
| `meta/objects/chunk/<n>` | META_CHUNK | schema_service.handle_chunk() |
| `status/online` | STATUS | house_service.handle_status() |
| `cmd/ack/<request_id>` | CMD_ACK | command_service.handle_ack() |
| `rpc/resp/<client_id>/<request_id>` | RPC_RESP | rpc_service.handle_resp() |

---

## Message Schemas

### EVENT (events)

```json
{
  "ts": 1730000000,
  "seq": 123456,
  "type": "knx.groupwrite",
  "ga": "1/1/1",
  "id": 2305,
  "name": "Свет - крыльцо",
  "datatype": 1001,
  "value": true
}
```

Required: `ts`
Optional: all other fields

### STATE (state/ga/*)

```json
{
  "ts": 1730000000,
  "value": true,
  "datatype": 1001
}
```

Required: `ts`, `value`, `datatype`

### META_FULL (meta/objects)

```json
{
  "ts": 1730000000,
  "schema_version": 1,
  "schema_hash": "sha256:...",
  "count": 189,
  "objects": [
    {
      "id": 2305,
      "address": "1/1/1",
      "name": "Свет - крыльцо",
      "datatype": 1001,
      "units": "",
      "tags": "control, light, outside",
      "comment": ""
    }
  ]
}
```

Required: `ts`, `schema_hash`, `count`, `objects`

### META_CHUNK (meta/objects/chunk/N)

```json
{
  "ts": 1730000000,
  "schema_version": 1,
  "schema_hash": "sha256:...",
  "count": 189,
  "chunk_no": 1,
  "chunk_total": 3,
  "objects": [...]
}
```

Required: `ts`, `schema_hash`, `count`, `chunk_no`, `chunk_total`, `objects`

### STATUS (status/online)

Online:
```json
{"ts": 1730000000, "status": "online", "version": "1.0.0"}
```

Offline (LWT):
```json
{"ts": 1730000000, "status": "offline"}
```

Required: `ts`, `status`

### CMD (cmd) — published by server

Single:
```json
{"request_id": "uuid", "ga": "1/1/1", "value": 1}
```

Batch:
```json
{
  "request_id": "uuid",
  "items": [
    {"ga": "1/1/1", "value": 1},
    {"ga": "2/1/10", "value": 21.5}
  ]
}
```

Required: `request_id`, (`ga` + `value`) or `items`

### CMD_ACK (cmd/ack/*)

```json
{
  "ts": 1730000000,
  "request_id": "uuid",
  "status": "ok",
  "results": [
    {"ga": "1/1/1", "applied": true, "error": null}
  ]
}
```

Required: `ts`, `request_id`, `status`

### RPC_REQ (rpc/req/*) — published by server

```json
{
  "request_id": "uuid",
  "method": "snapshot",
  "params": {"scope": "all"}
}
```

### RPC_RESP (rpc/resp/*/*)

```json
{
  "request_id": "uuid",
  "ok": true,
  "chunk_no": 1,
  "chunk_total": 1,
  "result": {}
}
```
