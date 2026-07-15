# House objects inventory (climate / light / sensors)

**Date:** 2026-07-15  
**Source (live):** [`docs/cottage-monitoring-export-live.json`](../../cottage-monitoring-export-live.json) — `export.lp?action=export_file` from LM `192.168.100.130` (204 objects, 2026-07-15)  
**Source (legacy):** [`docs/objects.json`](../../objects.json) — older raw `grp.all()` snapshot (212), outdated for teapot  
**Purpose:** Ground MCP semantic tools (`set_climate`, `set_light`, `get_temperature`, …) in real tags/names — no invented GAs.

**How to refresh live export:**
```bash
curl --basic -u 'admin:…' \
  -H 'Referer: http://192.168.100.130/apps/data/cottage-monitoring/index.lp' \
  'http://192.168.100.130/apps/data/cottage-monitoring/export.lp?action=export_file' \
  -o docs/cottage-monitoring-export-live.json
```
Without `Referer` LM returns HTTP 400 for executable `.lp` endpoints.

## Summary counts

| Kind | Count | How detected |
|------|------:|--------------|
| Light control (writable) | 20 | tags `control` + `light` |
| Light status | 20 | tags `status` + `light` |
| Floor temperature | 14 | `temp` + `heat`, not `setpoint` |
| Heat setpoint (writable °C) | 14 | tag `setpoint` |
| Heat relay control | 13 | `control` + `heat` |
| Heat relay status | 13 | `status` + `heat` |
| Air / weather temp-like | 11 | `temperature` or outdoor `temp`+`weather` |
| Humidity | 10 | tag `humidity` |
| Electric meter points | 46 | tag `meter` |
| Weather (non-temp) | 5 | `weather` without classified above |
| Monitoring / diagnostics | 5 | tag `monitoring` |

### Top tags

`heat` 71 · `meter` 46 · `light` 40 · `1floor` 39 · `control` 34 · `2floor` 34 · `status` 34 · `temp` 30 · `zb_sensor` 27 · `setpoint` 14 · `humidity` 10 · `temperature` 9 · `weather` 8 · `monitoring` 5 · `auto` 1

## Light

**Write:** GA family `1/1/*` — names `Свет - <room>`, tags include `control,light` (+ `1floor`/`2floor`/`outside`, sometimes `zigbee`).

Examples:

| GA | Name | Tags |
|----|------|------|
| `1/1/1` | Свет - крыльцо | control, light, outside |
| `1/1/6` | Свет - гостиная | 1floor, control, light |
| `1/1/7` | Свет - кухня | 1floor, control, light |
| `1/1/18` | Свет - гостиная - торшер | … zigbee |

**Read feedback:** `1/2/*` — same room name + `:status`, tags `light,status` (**no** `control`). MCP `set_light` must resolve **control**, not status.

Room matching works well via Russian substrings in `name` (`кухня`, `тамбур`, `кабинет`, …). Ambiguity example: «гостиная» → main light + торшер (+ гостиная1/2 for heat).

## Climate (тёплые полы) — алгоритм `manage_warm_floor.lua`

**Не HVAC с режимами fan/cool** — плёночные тёплые полы с авто-балансировкой.

### Как работает (из Lua)

| GA / объект | Роль |
|-------------|------|
| `1/7/1` | **Автоуправление** (`auto,heat`). Если `false` — скрипт гасит все реле и выходит. **Не переключать агентом без явной просьбы.** |
| `1/6/*` | **Уставка** (комнатная цель). Запись уставки **не включает** пол. |
| `1/4/*` | **Реле** (`control,heat`). В штатном режиме включает **только алгоритм** (лимит мощности, Zigbee/fallback). Ручное включение — **отладка**. |
| `1/5/*` | Статус реле |
| `1/3/*` | **Температура в плёнке пола** (не воздух в комнате) |
| `33/1/*` + `temperature` | **Температура воздуха** Zigbee — основной источник для комфорта и для алгоритма (режим zigbee) |
| `33/1/*` + `humidity` | Влажность воздуха |
| `34/1/*` | Готовая диагностика (режимы, блокировки, погода, мощность) |

Алгоритм: при свежем Zigbee управляет по **воздуху**; при протухшем — fallback по **полу** с effective_sp = setpoint + k + kw_base×w. Реле распределяются по приоритету и лимиту `32/6/1` (9103 W).

### Setpoints (primary `set_climate` target)

GA `1/6/2`…`1/6/15`, tags `heat,setpoint,temp` + floor tag, names `Уставка ТП - <room>`, values ~19–26 °C.

| GA | Room (from name) | Example value |
|----|------------------|--------------:|
| `1/6/2` | тамбур | 23 |
| `1/6/4` | спальня | 21 |
| `1/6/5` | гостиная 1 | 23 |
| `1/6/6` | гостиная 2 | 23 |
| `1/6/7` | кухня | 23 |
| `1/6/11` | гостевая | 19 |
| `1/6/12` | Настина комната | 22 |
| `1/6/13` | Тимнина комната | 22 |
| `1/6/15` | кабинет | 22 |

### Relays

- Control `1/4/*`: `ТП - <room>`, tags `control,heat` (bool)
- Status `1/5/*`: `ТП - <room> :status`, tags `heat,status`

### Special

| GA | Name | Notes |
|----|------|--------|
| `1/6/1` | Уставка ТП - master | value 24; **empty tags** — hide from default discover |
| `1/7/1` | Автоматическое управление отоплением | tags `auto,heat`; bool — global auto; do not toggle casually from voice without confirm |

### Floor temperature sensors

`1/3/2`…`1/3/15` — `Темп - <room>`, tags `heat,temp` (+ floor). These are floor (or zone) temps used by heating logic — **not** setpoints.

Raw ints on `32/3/*` (`Темп - … (raw)`, tag `heat` only) — exclude from default `get_temperature` (noise).

## Air temperature & humidity (Zigbee)

Family `33/1/*`, tags `zb_sensor` + `temperature` / `humidity` / `battery` + `floor1`/`floor2`. English technical names (`zb_sensor_fl1_living_room_temperature`). Prefer these when user asks for «температура воздуха» / comfort.

## Weather / outdoor

`32/5/*`: outside temp, feels-like, humidity, pressure, wind — tags `outside,weather,…`. Include in `get_temperature` / `get_sensors` when query is «улица» / «погода».

## Energy (электросчётчик `32/1/*`)

MCP tool `get_energy_status` отдаёт curated набор:

| GA | Параметр |
|----|----------|
| `32/1/35` | Total P (W) |
| `32/1/36–38` | Total Q, S, PF |
| `32/1/39` | Total AP energy (kWh) |
| `32/1/7` | Frequency (Hz) |
| `32/1/1,3,5` | Urms L1–L3 |
| `32/1/11,19,27` | Irms L1–L3 |
| `32/1/13,21,29` | P L1–L3 |
| `32/1/57–59` | consumption Hour / Daily / Total |

## Smart kettle (BLE Redmond RK-M173S)

Live export:

| GA | Name | Tags | Role |
|----|------|------|------|
| `33/1/37` | `ble_teapot_RK-M173S_temp` | `ble, teapot, temp` | температура воды (°C) |
| `33/1/38` | `ble_teapot_RK-M173S_state` | `ble, status, teapot` | status (bool) |
| `33/1/39` | `ble_teapot_RK-M173S_cmd` | `ble, control, zigbee_send` | **write** on/off |

MCP: `set_kettle` → только `…_cmd` (`33/1/39`). Status/temp — read via `get_sensors` / discover `teapot`.

## Extra rooms / sensors (new vs legacy snapshot)

Live export added Zigbee halls/bathrooms and load avg: `33/1/28–36`, `34/1/5` (ТП текст), `34/1/6–8` (load 1/5/15 min). Legacy raw ints `32/3/*` and some stub GAs dropped from active schema.

## Heating diagnostics (`34/1/*`)

## Resolver implications

1. **Kinds must distinguish** `control` vs `status` vs `setpoint` — never write to status GAs.
2. **Climate write default = setpoint**, not relay (auto heating usually owns relays). Optional `heating_on` for explicit override.
3. **Temperature read** should label source: `floor` (`1/3`), `air` (`33/1` + `temperature`), `outdoor` (`weather`).
4. **Synonyms to document in skill:** зал/гостиная; Настя/Настина; Тим/Тимина/Тимнина (note spelling variants in names).
5. **Master / auto** — discover only if query explicitly mentions them; skill: ask before changing auto.

## Gaps / follow-ups (non-blocking)

- No separate DPT “climate mode” besides auto bool + setpoints.
- `1floor` vs `floor1` tag inconsistency (KNX vs Zigbee) — resolver should accept both.
- Empty-name / empty-tag orphans (e.g. some `32/1/50`) — ignore if inactive or nameless.
