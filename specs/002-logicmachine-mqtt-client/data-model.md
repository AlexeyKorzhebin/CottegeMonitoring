# Data Model: Logic Machine MQTT Client App

**Date**: 2026-03-03 | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

---

## Обзор

Приложение Logic Machine **не имеет собственной БД**. Все данные:
- **Конфигурация** — через `config.get/set` (LogicMachine Apps config API)
- **Буфер при offline** — RAM-таблица (Lua table)
- **Объекты KNX** — через `grp.all()` / `grp.find()` (runtime, не хранятся приложением)

---

## Конфигурация (config)

Хранится на контроллере через `config.get('cottage-monitoring', key, default)`.

### Обязательные поля

| Ключ | Тип | Описание | Пример |
|------|-----|----------|--------|
| house_id | string | ID дома в системе мониторинга | `house-01` |
| device_id | string | ID контроллера в рамках дома | `lm-main` |
| env_mode | string | `dev` \| `prod` — префикс топиков | `prod` |
| mqtt_host | string | Хост MQTT-брокера | `elion.black-castle.ru` |
| mqtt_port | string/number | Порт (8883 для TLS) | `8883` |
| mqtt_username | string | Логин MQTT | `cottage_client` |
| mqtt_password | string | Пароль MQTT | `***` |
| mqtt_use_tls | string | `true` — TLS обязателен | `true` |

### Опциональные поля

| Ключ | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| client_id | string | `house_id` + `-` + `device_id` | MQTT Client ID |
| debug | string | `false` | Включить log/alert |
| snapshot_interval | number | 0 | Интервал snapshot (с), 0 = выключено |
| throttle | number | 0 | Макс. events/с, 0 = без ограничения |
| buffer_size | number | 1000 | Размер буфера при offline, 0 = отключён |

### Валидация (config-check)

- `house_id`, `device_id`: не пусто, до 64 символов, `[a-zA-Z0-9_-]+`
- `env_mode`: `dev` или `prod`
- `mqtt_port`: 1–65535
- `mqtt_username`, `mqtt_password`: не пусто
- `snapshot_interval`, `throttle`, `buffer_size`: ≥ 0

---

## Буфер (RAM)

При `buffer_size > 0` и отключённом MQTT записи накапливаются в таблице:

```lua
buffer = {
  { topic = "...", payload = "{...}", qos = 1, retain = true/false },
  ...
}
```

Каждая запись — отдельное сообщение (event + state или иное). FIFO, без дедупликации.

---

## Модель объекта KNX (для meta/state/events)

Используется при сериализации в JSON для MQTT. Источник: `grp.find()`, `grp.all()`.

| Поле | Тип | Описание |
|------|-----|----------|
| id | number | object_id на контроллере |
| address | string | Group Address (1/1/1) |
| name | string | Имя объекта |
| datatype | number | KNX datatype (1001, 9001, 14...) |
| units | string | Единицы измерения |
| tags | string | Теги через запятую |
| comment | string | Комментарий |
| value | any | Текущее значение (для state/snapshot) |
| ts | number | Unix timestamp |

---

## Топики MQTT (ссылка)

См. [../001-server-mqtt-ingestor/contracts/mqtt-topics.md](../001-server-mqtt-ingestor/contracts/mqtt-topics.md).

**Prefix**:
- `env_mode=prod` → без префикса: `cm/<house_id>/<device_id>/v1/...`
- `env_mode=dev` → `dev/` + `cm/...`: `dev/cm/<house_id>/<device_id>/v1/...`
