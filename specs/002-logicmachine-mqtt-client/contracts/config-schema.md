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
| throttle | number | | ≥ 0, 0 = без ограничения; default **20** |
| buffer_size | number | | ≥ 0, 0 = буфер отключён |
| batch_interval | number | | ≥ 0, с; 0 = immediate dual-publish; default **1.5** |
| batch_max_size | number | | ≥ 0; сброс буфера по размеру; default **50** |
| event_sleep | number | | 0–1, пауза (с) после каждого KNX groupwrite, 0 = off. Default **0.03** |
| loop_sleep | number | | 0.01–0.5, пауза (с) в главном цикле. Default **0.25** |

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
  "throttle": 20,
  "buffer_size": 1000,
  "batch_interval": 1.5,
  "batch_max_size": 50,
  "event_sleep": 0.03,
  "loop_sleep": 0.25
}
```

---

## config-check (клиентская валидация)

При невалидных данных — `alert('...')` и **не** вызывать `config-save`.
При успехе — `el.triggerHandler('config-save', { ... })`.
