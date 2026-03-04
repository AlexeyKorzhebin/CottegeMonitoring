# MQTT Protocol: Logic Machine Client → Server

**Спецификация**: [../001-server-mqtt-ingestor/contracts/mqtt-topics.md](../001-server-mqtt-ingestor/contracts/mqtt-topics.md)

Данный документ — краткая ссылка на контракт для реализации клиента.

---

## Namespace

```
{prefix}cm/<house_id>/<device_id>/v1/
```

- `prefix`: `dev/` при env_mode=dev, пусто при prod
- `house_id`, `device_id` — из конфига

---

## Publications (Client publishes)

| Topic | QoS | Retain | Когда |
|-------|-----|--------|-------|
| `.../events` | 0/1 | no | При каждом groupwrite |
| `.../state/ga/<ga>` | 1 | yes | При groupwrite + при snapshot |
| `.../meta/objects` | 1 | yes | При старте, при изменении схемы, если ≤100 объектов |
| `.../meta/objects/chunk/<n>` | 1 | yes | При >100 объектах |
| `.../status/online` | 1 | yes | При connect + LWT |
| `.../cmd/ack/<request_id>` | 0/1 | no | После выполнения cmd |
| `.../rpc/resp/<client_id>/<request_id>` | 0/1 | no | Ответ на rpc/req |

---

## Subscriptions (Client subscribes)

| Topic | QoS | Назначение |
|-------|-----|------------|
| `.../cmd` | 1 | Команды управления |
| `.../rpc/req/<client_id>` | 0/1 | RPC: meta, snapshot |

---

## Форматы payload

См. [../001-server-mqtt-ingestor/contracts/mqtt-topics.md](../001-server-mqtt-ingestor/contracts/mqtt-topics.md) — разделы Message Schemas.
