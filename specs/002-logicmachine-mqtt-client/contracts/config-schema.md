# Config Schema: Logic Machine MQTT Client App

**Form ID**: `cottage-monitoring-config` (или `<appname>-config`)

События формы: `config-load`, `config-check`, `config-save`.

---

## Поля формы (HTML/LP)

| name / id | Тип | Обязателен | Валидация |
|-----------|-----|------------|-----------|
| house_id | text | ✓ | 1–64 символа, `[a-zA-Z0-9_-]+` |
| device_id | text | ✓ | 1–64 символа |
| env_mode | select | ✓ | `dev` \| `prod` |
| mqtt_host | text | ✓ | домен или IP |
| mqtt_port | number | ✓ | 1–65535 |
| mqtt_username | text | ✓ | не пусто |
| mqtt_password | password | ✓ | не пусто |
| mqtt_use_tls | checkbox | ✓ | всегда включён (disabled) |
| client_id | text | | 0–64 символа (пусто = auto) |
| debug | checkbox | | |
| snapshot_interval | number | | ≥ 0, 0 = off |
| throttle | number | | ≥ 0, 0 = без ограничения |
| buffer_size | number | | ≥ 0, 0 = буфер отключён |

---

## Пример config-save payload (prod, LogicMachine)

```json
{
  "house_id": "house",
  "device_id": "lm-main",
  "env_mode": "prod",
  "mqtt_host": "elion.black-castle.ru",
  "mqtt_port": 8883,
  "mqtt_username": "lm_estate",
  "mqtt_password": "***",
  "mqtt_use_tls": true,
  "client_id": "auto",
  "debug": false,
  "snapshot_interval": 0,
  "throttle": 0,
  "buffer_size": 1000
}
```

---

## config-check (клиентская валидация)

При невалидных данных — `alert('...')` и **не** вызывать `config-save`.
При успехе — `el.triggerHandler('config-save', { ... })`.
