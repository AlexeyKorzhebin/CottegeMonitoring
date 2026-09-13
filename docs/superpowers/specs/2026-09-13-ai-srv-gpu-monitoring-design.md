# AI-SRV GPU monitoring — Design Spec

**Date:** 2026-09-13  
**Status:** Approved  
**Scope:** Logic Machine group objects + `mqtt_listen` mapping + Grafana dashboard for GPU host `alex-NEURO`.  
**Depends on:** cooler-arduino MQTT contract (`/Users/aleksey.korzhebin/Yandex.Disk.localized/Projects/cooler-arduino/docs/specification.md` §6); cottage-monitoring daemon already publishes all `groupwrite`; Grafana file provisioning.  
**Related:** `docs/superpowers/specs/2026-07-15-house-objects-inventory.md`, `server/deploy/grafana/README.md`.

---

## 1. Problem

В доме появился GPU-компьютер `alex-NEURO` (`192.168.100.50`). Он уже публикует телеметрию охлаждения, защиты и хоста в LAN MQTT на Logic Machine (`192.168.100.130:1883`), топики `cooler-arduino/alex-neuro` и `…/availability`, JSON в стиле `z2m_style`. Cottage Monitoring это не видит: `mqtt_listen` мапит Zigbee и реле, объектов GPU нет, отдельного дашборда Grafana нет.

Нужно: групповые адреса на LM, маппинг в существующем `mqtt_listen`, облако тем же путём, что свет и полы, отдельный дашборд Grafana.

---

## 2. Vocabulary

| Термин | Значение |
|--------|----------|
| **AI-SRV** | Префикс имён объектов GPU-компьютера в LM. Не hostname. |
| **KNX = облако** | `grp.update` → daemon `groupwrite` → MQTT `cm/house/…` → PostgreSQL → Grafana SELECT. Отдельного ingest мимо LM нет. |
| **Просадка** | Вместо пары значение+status в один адрес пишется живое число или **−1**, чтобы обрыв был виден на графике. |
| **`mqtt_listen`** | Resident LM id **4**. Не путать с `mqtt_listen copy` (id 48). |
| **Каталог** | Таблица 19 объектов: GA, имя, MQTT-поле, DPT, sentinel. Один источник для Lua, тестов и Grafana. |

Говорим: «AI-SRV в `35/1`, теги `monitoring, gpu, ai-srv`». Не говорим: «новый MQTT-клиент в облако» и не путаем с климатом `33/1`.

---

## 3. Goals

| Goal | Decision |
|------|----------|
| Объекты LM | 19 штук, `35/1/1`…`35/1/19`, одноразовый `grp.create` как `create z-sensors` |
| Имена | `AI-SRV - <метрика>` |
| Теги на всех | `monitoring, gpu, ai-srv` |
| Чтение MQTT | Дописать `mqtt_listen` id 4; два топика |
| Нет данных | Числа **−1**; serial/boot **unknown**; нет аварии в JSON **none**; online bool **false** |
| Облако | Только через существующий daemon |
| Grafana | Новый дашборд `cottage-ai-srv`, папка Cottage, ссылки в nav |
| Репозиторий | Каталог + Lua create + копия `mqtt_listen` в git |

---

## 4. Non-goals

- HA entities, новые Ops, `get_temperature` для GPU.
- Входящий MQTT / удалённое управление кулером (экспортёр publish-only).
- Правка cooler-arduino, firmware, guard.
- `mqtt_listen copy`.
- Адреса в `33/1` или `34/1`.
- Отдельные `*_status` GA.
- Telegram-алерты этой волной.
- Поля-константы MQTT: `schema_version`, `gpu_selector`, `pwm_kind`, `freshness_limit_seconds`, `gpu_name`, `disk_mount`, байты диска, RAM total/available, VRAM total, JSON `available` (дубль топика availability).

---

## 5. Approaches considered

| Подход | Суть | Решение |
|--------|------|---------|
| Прямой MQTT с elion на LAN-брокер | Второй ingest | Нет |
| Все поля JSON + все `*_status`/`*_age` | ~50 GA | Нет |
| Пара значение + status | Два объекта на метрику | Нет: просадка −1 |
| Объекты в `34/1/9+` с тегом `monitoring` | Рядом с loadavg | Нет: resolver `34/1`+`monitoring` = диагностика ТП |
| Тег `monitoring` при адресах `35/1` | Общий фильтр в LM | **Да** |
| Создание кликами в UI | 19 объектов вручную | Нет: скрипт `grp.create` |

---

## 6. Architecture

```text
alex-NEURO  cooler-mqtt  →  LAN MQTT 192.168.100.130:1883
                              cooler-arduino/alex-neuro
                              cooler-arduino/alex-neuro/availability
                                    │
                                    ▼
                         LM mqtt_listen (resident 4)
                              grp.update 35/1/*
                                    │
                                    ▼
                         cottage-monitoring daemon
                              cm/house/…/events + state
                                    │
                                    ▼
                         elion PostgreSQL / Grafana cottage-ai-srv
```

Создание объектов: одноразовый user-script, не resident. Повторный запуск пропускает существующий адрес.

После смены `statusmap` resident 4 нужно перезапустить, иначе subscribe не обновится.

---

## 7. Group objects

Теги всех: `monitoring, gpu, ai-srv`.  
Без `temp`, `temperature`, `zb_sensor`, `heat`, `light`, `host`, `alex-neuro`.  
Comment: `source: cooler-arduino/alex-neuro`.

Числовые DPT — **9** (2-byte float, как loadavg `34/1/6`), не DPT 5: иначе −1 не записать.  
Bool online — **1.001**.  
Строки — **255**, как «ТП Диагностика - текст» (DPT 16 = 14 символов, UUID/event_id не влезут).

| GA | Имя | MQTT | DPT | Нет данных | Живое |
|----|-----|------|-----|------------|-------|
| `35/1/1` | AI-SRV - online | топик availability | 1.001 | false | true если `online` |
| `35/1/2` | AI-SRV - температура | `temperature` °C | 9.001 | −1 | 30…84 |
| `35/1/3` | AI-SRV - RPM | `rpm` | 9 | −1 | 0 = стоит |
| `35/1/4` | AI-SRV - PWM | `pwm` | 9 | −1 | 0…255 команда |
| `35/1/5` | AI-SRV - serial | `serial_state` | 255 | unknown | connected / error |
| `35/1/6` | AI-SRV - защита | `protection_state` | 255 | unknown | monitoring / sensor_unavailable / alarm |
| `35/1/7` | AI-SRV - потеря датчика с | `sensor_loss_elapsed_seconds` | 9 | −1 | 0 = отказа нет |
| `35/1/8` | AI-SRV - GPU % | `gpu_utilization_percent` | 9 | −1 | 0 = idle |
| `35/1/9` | AI-SRV - VRAM GiB | `gpu_memory_used_mib / 1024` | 9 | −1 | 0…64 |
| `35/1/10` | AI-SRV - мощность Вт | `gpu_power_draw_w` | 9 | −1 | ватты |
| `35/1/11` | AI-SRV - CPU % | `cpu_utilization_percent` | 9 | −1 | 0 = idle |
| `35/1/12` | AI-SRV - RAM GiB | `ram_used_bytes / 1073741824` | 9 | −1 | GiB |
| `35/1/13` | AI-SRV - диск % | `disk_used_percent` | 9 | −1 | 0…100 |
| `35/1/14` | AI-SRV - boot id | `boot_id` | 255 | unknown | UUID |
| `35/1/15` | AI-SRV - авария причина | `last_shutdown_reason.reason` | 255 | none | overheat / sensor_loss |
| `35/1/16` | AI-SRV - авария id | `last_shutdown_reason.event_id` | 255 | none | event_id |
| `35/1/17` | AI-SRV - авария статус | `last_shutdown_reason.status` | 255 | none | request_* |
| `35/1/18` | AI-SRV - авария температура | `last_shutdown_reason.last_temperature_c` | 9.001 | −1 | °C в момент аварии |
| `35/1/19` | AI-SRV - авария время | `last_shutdown_reason.timestamp_utc` | 255 | none | UTC аварии |

`35/1` на живой LM пуст. Заняты: `1/*`, `32/1`, `32/4–6`, `33/1/1–39`, `34/1/1–8`.

---

## 8. Mapping rules (`mqtt_listen`)

Топики (точное совпадение, как сейчас у Zigbee):

- `cooler-arduino/alex-neuro`
- `cooler-arduino/alex-neuro/availability`

Существующие записи `statusmap` не менять.

**Availability.** Payload не JSON. `online` → `grp.update('35/1/1', true)`. Иначе → `false`. При `false` дополнительно записать **−1** во все числовые GA `35/1/2–4`, `35/1/7–13`, `35/1/18` (не трогать строки аварии 15–17, 19 и boot 14: история и boot_id не «протухают» от LWT).

**JSON.** `json.pdecode`. Число в GA, если значение не null **и** соответствующий `*_status` отсутствует или равен `fresh`. Иначе −1. Поля без `*_status` в контракте (`pwm`, `serial_state`, `protection_state`, `boot_id`, `sensor_loss_elapsed_seconds`): null → sentinel; `sensor_loss_elapsed_seconds == null` → **0** (отказа нет), не −1; неизвестность этого поля только если JSON не разобрали.

VRAM: `gpu_memory_used_mib / 1024`. RAM: `ram_used_bytes / 1073741824`.

**`last_shutdown_reason`.** Верхний уровень — объект, текущий цикл `pairs(dd)` в GA таблицу не разложит. После decode, если поле `null`/нет — `none` / −1 на 15–19. Если таблица — пять ключей в 15–19. Не писать вложенный JSON целиком в один адрес.

**Протухший retained.** Если `temperature_status ~= 'fresh'` (и аналогично rpm/gpu/cpu/power) — −1, даже если число есть. Отдельную сверку часов LM с UTC не делаем: статус экспортёра уже свёрнут.

Zigbee-ветка `grp.update` для JSON и `grp.checkupdate` для сырых реле — не менять поведение реле. Для AI-SRV использовать `grp.update`, чтобы −1 гарантированно ушёл в daemon.

---

## 9. Grafana

- UID `cottage-ai-srv`, title `Cottage — AI-SRV`.
- Tags дашборда: `cottage`, `gpu`, `ai-srv`.
- Refresh 30s.
- Nav: ссылка во все Cottage-дашборды, включая этот.
- Панели: сейчас (online, температура, RPM, PWM, serial, защита); графики температуры/RPM/PWM; GPU % / VRAM / мощность; CPU / RAM / диск; блок последней аварии (причина, статус, температура, время, id).
- SQL как у LM Load: `events` + `current_state`, `house_id = 'house'`, GA `35/1/*`.
- −1 на графиках не прятать: это сигнал дыры. Порог температуры 84 °C — линия на графике, без Telegram-алерта в этой волне.
- Деплой: `./server/deploy/grafana/deploy.sh` (generate + scp на elion). Код приложения Nord не трогать, новый Docker-образ не нужен.

---

## 10. Testing

- Python: каталог 19 объектов; convert (fresh/null/status); GiB; availability offline → числа −1; Lua create/`mqtt_listen` содержат все GA каталога.
- Grafana generate: UID `cottage-ai-srv` в JSON, GA `35/1/2` в SQL.
- Live: после create+restart `mqtt_listen` — объекты в `grp`, значения не все −1 при живом экспортёре; через минуту `current_state` на elion; дашборд открывается.

---

## 11. Deploy LM

1. Залить и один раз выполнить `create-ai-srv-objects.lua`.
2. Залить обновлённый `mqtt_listen` в scripting id 4 (FTP + `.lp` `db:update`, как watchdog).
3. Перезапустить resident 4 (нужен живой SSH `lm_estate` или HTTP-рестарт; если SSH ключ не принимает — `.lp`/ручной respawn, не оставлять старый процесс).
4. Не рестартовать cottage-monitoring daemon без нужды: новые GA подхватит schema/groupwrite.

Пароли LM только из `secrets/lm.env`. Dump-скрипты с LM после работы удалять.
