# HA Energy, Batteries, Grafana — Design Spec

**Date:** 2026-08-28  
**Status:** Implemented  
**Live (elion 2026-08-28):** Nord `cottage-monitoring:0.3.4`; Счётчик = `sensor.schetchik`; Energy grid настроен; 6 energy + 12 battery entities. Grafana `allow_embedding=true` (без anonymous). Lovelace «Графики»: iframe + markdown-ссылки; cookie `ha.`→`elion.` может опустошить iframe — fallback-ссылки — основной рабочий путь. Август в штатном Energy: backfill hourly LTS из Timescale `32/1/59` (`import-meter-lts.py`), ~500 кВт·ч за месяц, не ждать recorder с нуля.  
**Scope:** Шесть энергетических сенсоров в семейной витрине HA + штатный Energy; батареи Zigbee в комнатах; вкладка Lovelace с графиками Grafana.  
**Depends on:** [2026-08-28-ha-nord-design.md](./2026-08-28-ha-nord-design.md) (витрина HA, poll Ops, Areas/Floors).  
**Related:** [2026-08-27-nord-ops-design.md](./2026-08-27-nord-ops-design.md), `get_energy_status` / `get_sensors` в каталоге Ops, Grafana `cottage-energy` / `cottage-batteries`.

---

## 1. Problem

Витрина HA уже показывает свет, климат, датчики воздуха/пола и чайник. Электричество семья смотрит в Grafana (плитки Electricity) или спрашивает Telegram (`get_energy_status`). Батареи Zigbee есть в Grafana Batteries и в объектах LM (`zb_sensor_*_battery`), в HA их нет.

Нужно: текущее потребление, частота, показания счётчика для ЖКХ, расход за час и за сутки — в HA, без фаз и без второго протокола. Графики «как в Grafana» не дублировать SQL в HA: встроить готовые дашборды. Мозг дома по-прежнему LogicMachine; Grafana — SELECT.

---

## 2. Vocabulary

| Термин | Значение |
|--------|----------|
| **Шесть чисел** | Сейчас (Вт), Частота (Гц), Счётчик (кВт·ч), За час, За сутки, PF. Только они в HA. |
| **Счётчик ЖКХ** | Регистр `32/1/59` (consumption Total). Не `32/1/39` (другой AP energy). |
| **Energy HA** | Штатный раздел Home Assistant Energy. Источник сетки — счётчик `32/1/59`; живая мощность — «Сейчас». |
| **Вкладка Графики** | Lovelace view в HA: iframe Grafana или ссылка, если iframe не авторизуется. |

Говорим: «энергия через тот же `get_energy_status`, что Telegram». Не говорим «HA считает кВт·ч сам из MQTT».

---

## 3. Goals

| Goal | Decision |
|------|----------|
| Текущее потребление | Sensor **Сейчас**, `32/1/35` Total P, Вт, `device_class` power |
| Частота | Sensor **Частота**, `32/1/7`, Гц |
| ЖКХ | Sensor **Счётчик**, `32/1/59`, кВт·ч, `state_class` total_increasing — корм Energy HA |
| Последний час / сутки | **За час** `32/1/57`, **За сутки** `32/1/58` — регистры счётчика, не интеграл в HA |
| PF | Sensor **PF**, `32/1/38`, без единицы |
| Батареи в комнате | Sensor **Батарея**, %, та же area, что воздух |
| Графики | Вкладка Lovelace → Grafana Electricity (и Batteries). Grafana SELECT |
| Один каталог | HA poll `get_energy_status` + `get_sensors` kind батареи. Новых write-Ops нет |
| Без GA в UI | `unique_id` = `{house_id}:energy:{key}` / `{house_id}:sensor_battery:{slug}` |

---

## 4. Non-goals

- Фазы L1–L3 (U/I/P), Total Q, Total S, регистр `32/1/39` — только Grafana.
- MQTT `ha/#` / `cm/#`, push вместо poll 30 с.
- Картинки этажей, ручной Lovelace-план.
- Users в Nord; аккаунты семьи HA People.
- Уставка чайника на LM.
- Config flow компонента (warning 2027.8) — не эта волна.
- Анонимный Grafana на весь инстанс. Если iframe без сессии пустой — **ссылка**, не открывать Grafana без логина в интернет.

---

## 5. Approaches considered

| Подход | Суть | Решение |
|--------|------|---------|
| YAML REST sensors на каждый GA | Дублирует каталог | Нет |
| HA интегрирует счётчик по MQTT | Второй протокол | Нет |
| **Poll `get_energy_status`, в snapshot только 6 GA (выбран)** | Telegram по-прежнему видит полный items[] | Да: фильтр в HA, Op не режем |
| Считать час/сутки в HA из `32/1/59` | Расходится со счётчиком | Нет: берём `32/1/57` и `32/1/58` |
| **Штатный Energy HA + шесть карточек в area «Дом» (выбран)** | Семья: плитки и графики дней | Да |
| Копировать SQL Grafana в Lovelace | Два источника правды | Нет |
| **iframe Grafana; fallback — ссылка (выбран)** | Те же дашборды | Да. `allow_embedding` с `ha.black-castle.ru`. Cross-subdomain cookie может сломать iframe — тогда кнопка на `https://elion.black-castle.ru/grafana/d/cottage-energy/` |
| `get_sensors` kind=sensor и фильтр в HA | Лишние PIR/illuminance | Нет: kind=`battery`, как humidity |

---

## 6. Architecture

```text
Семья  HA  https://ha.black-castle.ru
        │ poll 30 с  (+2 read Ops)
        ▼
Nord  get_energy_status     полный items[]  (Telegram без изменений)
      get_sensors battery   tag/name battery + area/floor
        │
        ▼
HA snapshot  6 energy keys + battery sensors
        ├── area «Дом»: Сейчас, Частота, Счётчик, За час, За сутки, PF
        ├── Energy HA: grid = Счётчик, power = Сейчас
        ├── комнаты: Батарея
        └── Lovelace «Графики»: iframe / ссылка Grafana SELECT
```

Nord `get_energy_status` и список `ENERGY_SUMMARY_GAS` не сужаем: фазы остаются для Telegram и Grafana SQL.

---

## 7. Energy mapping (HA)

Area: **Дом** (уже есть: Онлайн, Автополы). Имена короткие, как воздух/пол.

| unique key | GA | Имя | unit / class |
|------------|-----|------|----------------|
| `power` | `32/1/35` | Сейчас | W, power, measurement |
| `frequency` | `32/1/7` | Частота | Hz, frequency, measurement |
| `meter` | `32/1/59` | Счётчик | kWh, energy, total_increasing |
| `hour` | `32/1/57` | За час | kWh, energy, total (окно счётчика, не monotonic lifetime) |
| `daily` | `32/1/58` | За сутки | kWh, energy, total |
| `pf` | `32/1/38` | PF | без unit, measurement |

`hour` / `daily` — показания регистров «за период» на стороне счётчика; не `total_increasing`, чтобы recorder не ждал вечный рост.

Конфиг Energy HA (`.storage/energy` / UI): источник потребления сети = entity **Счётчик**. Живая мощность = **Сейчас**. Стоимость тарифа не заводим (нет в Ops).

Если GA нет в `items[]` — сущность не создаём (как с отсутствующим чайником).

---

## 8. Batteries

- `get_sensors` с `kind=battery`: тот же приём, что `kind=humidity` — `DiscoverKind.SENSOR` + роль/тег батареи (`battery` в tags или имя `*_battery`). При необходимости роль `room_battery` рядом с `room_humidity`.
- `area` / `floor` из существующего `placement.py` (regex уже включает `battery`).
- HA: `device_class` battery, `%`, имя **Батарея**. unique_id `house:sensor_battery:{slug(name)}`.
- Нет area (серверная и т.п.) — `place_device_name`, как у воздуха.

---

## 9. Grafana Lovelace

- Новая view **Графики** (не ломать Overview / избранное Онлайн+Автополы).
- Карточки: Electricity `cottage-energy`; вторая — Batteries `cottage-batteries`. URL канона: `https://elion.black-castle.ru/grafana/d/<uid>/`.
- Grafana: `allow_embedding=true`, не открывать `/grafana` анонимно на весь инстанс.
- Если iframe показывает логин Grafana (другой host, чем HA) — view содержит markdown/кнопку со ссылкой, не пустую рамку. Проверка на elion обязательна до «готово».

---

## 10. HA component / poll

Coordinator сегодня: 6 Ops. Добавить:

1. `get_energy_status` (без тела).
2. `get_sensors` `{"kind": "battery"}` (второй вызов рядом с humidity, не смешивать в одном kind).

Каталог Ops по-прежнему 17 имён; новых Ops нет. `get_energy_status` уже в каталоге — только начать звать из HA.

Snapshot: типы energy + `kind=battery` у сенсоров. `sensor_display_name` для battery → «Батарея».

Energy dashboard: записать после появления entity_id счётчика (скрипт выкладки или ручной UI один раз; канон entity_id зафиксировать в quickstart).

---

## 11. Errors

| Ситуация | Поведение |
|----------|-----------|
| `get_energy_status` 5xx / сеть | Как остальные Ops: coordinator `UpdateFailed`, карточки unavailable |
| Нет одного GA из шести | Остальные пять живы |
| Нет battery objects | Платформа sensor просто без этих entity |
| Grafana iframe 401 | Fallback-ссылка, не «успешный» пустой iframe |

Write-Ops энергии нет.

---

## 12. Testing

- Snapshot: из фикстуры `get_energy_status.items` получаются ровно 6 ключей; `32/1/39` и фазы отброшены.
- Имена: Сейчас / Частота / Счётчик / За час / За сутки / PF.
- `sensor_display_name(..., kind="battery")` → «Батарея».
- Nord: `get_sensors` kind=battery возвращает объекты с tag/name battery и `area`/`floor` где placement знает комнату (тест резолвера/placement).
- Drift каталога: 17 имён, `get_energy_status` на месте.
- На elion: dry-run `get_energy_status`; в HA area Дом видны шесть чисел; Energy показывает сетку; в комнате спальня есть Батарея; вкладка Графики — iframe или рабочая ссылка.

---

## 13. Success criteria

1. В HA, area «Дом»: Сейчас, Частота, Счётчик, За час, За сутки, PF — без GA в названии.
2. Settings → Energy использует **Счётчик** как grid consumption.
3. В комнатах с Zigbee-датчиком — **Батарея** (%).
4. Вкладка **Графики** открывает Grafana Electricity (iframe или ссылка). Grafana не пишет команды.
5. Telegram `get_energy_status` по-прежнему полный набор items (включая фазы).

---

## 14. Implementation order

1. Nord: `get_sensors` kind=battery (+ роль/тесты placement).
2. HA snapshot + coordinator + sensor entities (энергия и батареи). TDD.
3. Energy HA config на volume.
4. Lovelace view Графики + Grafana `allow_embedding`.
5. Quickstart / research (R-xxx): entity_id, UID дашбордов, fallback ссылки.

---

## 15. Risks

| Risk | Mitigation |
|------|------------|
| `hour`/`daily` как total_increasing ломает статистику | class `total` / measurement, не lifetime |
| Перепутать `32/1/39` и `32/1/59` | В HA только allowlist; 59 = ЖКХ |
| iframe Grafana без cookie | Fallback-ссылка; не anonymous Grafana |
| Poll +2 Ops упирается в rate limit | Read; свой ключ HA; 30 с как сейчас |
| Battery kind ломает humidity call | Два раздельных `call_op`, не один kind |
