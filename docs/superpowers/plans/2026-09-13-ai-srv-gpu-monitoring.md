# AI-SRV GPU Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking. Do not offer inline execution. Do not use `inherit` for subagent models; pick from `.cursor/rules/subagent-models.mdc`.

**Goal:** 19 групповых адресов `35/1/1–19` на Logic Machine, маппинг MQTT кулера в `mqtt_listen`, дашборд Grafana `cottage-ai-srv`.

**Architecture:** JSON каталог — источник GA/имён/тегов. Lua `grp.create` (один раз) и resident `mqtt_listen` id 4 пишут в эти GA. Daemon уже публикует groupwrite в облако. Grafana SELECT по `events`/`current_state`.

**Tech Stack:** Python 3.12, pytest, ruff; Lua 5.1 on Logic Machine (`grp`, `mosquitto`, `json`); Grafana file provisioning.

**Spec:** `docs/superpowers/specs/2026-09-13-ai-srv-gpu-monitoring-design.md`

---

## Global Constraints

- Префикс имён: **`AI-SRV - `** (пробел-дефис-пробел). Не `alex-neuro` в имени.
- Теги всех 19: **`monitoring, gpu, ai-srv`**. Без `temp`, `temperature`, `zb_sensor`, `heat`, `light`, `host`.
- Адреса только **`35/1/1`…`35/1/19`**. Не `33/1`, не `34/1`.
- Sentinel чисел: **−1**. Исключение: `sensor_loss_elapsed_seconds` JSON `null` → **0**. Availability не `online` → `35/1/1=false` и −1 на числовые GA кроме строк аварии/boot.
- `mqtt_listen` **id 4** только. `mqtt_listen copy` id 48 не трогать. Существующие Zigbee/реле в `statusmap` не менять.
- KNX DPT: bool `1.001`; числа datatype **9** (температура 9.001); строки **255**.
- MQTT топики точно: `cooler-arduino/alex-neuro` и `cooler-arduino/alex-neuro/availability`.
- Grafana UID **`cottage-ai-srv`**. `house_id = 'house'`. Образ Nord / HA / новые Ops — нет.
- Не коммитить `investor-pitch/`, `docs/architecture/`, `secrets/`.
- Тесты: `cd server && python -m pytest <path> -v` затем `ruff check` на затронутый Python.
- Коммитить каждую задачу. Сообщение на английском, why-first, как в истории репо.

---

## File map

| Path | Role |
|------|------|
| `cm-client/scripts/ai_srv_catalog.json` | 19 объектов: ga, name, mqtt, dpt, kind |
| `server/src/cottage_monitoring/ai_srv_mapping.py` | load catalog + convert sentinels |
| `server/tests/unit/test_ai_srv_mapping.py` | convert + catalog size + classify OTHER |
| `cm-client/scripts/create-ai-srv-objects.lua` | one-shot `grp.create` |
| `cm-client/scripts/mqtt_listen.lua` | checked-in resident (Zigbee + AI-SRV) |
| `server/deploy/grafana/generate_dashboards.py` | `ai_srv()` + nav links |
| `server/deploy/grafana/dashboards/cottage_ai_srv.json` | generated |
| `server/deploy/grafana/README.md` | строка дашборда |
| `specs/001-server-mqtt-ingestor/quickstart.md` | Grafana UID |
| `specs/002-logicmachine-mqtt-client/quickstart.md` | LM scripts AI-SRV |

---

### Task 1: Catalog and sentinel mapping

**Files:**
- Create: `cm-client/scripts/ai_srv_catalog.json`
- Create: `server/src/cottage_monitoring/ai_srv_mapping.py`
- Create: `server/tests/unit/test_ai_srv_mapping.py`
- Modify: `server/tests/unit/test_object_resolver.py` (один тест classify)

**Interfaces:**
- Consumes: nothing
- Produces: `load_catalog() -> list[dict]`; `numeric_or_sentinel(value, status=None) -> float`; `sensor_loss_or_sentinel(value) -> float`; `mib_to_gib(value, status=None) -> float`; `bytes_to_gib(value, status=None) -> float`; `text_or_unknown(value) -> str`; `shutdown_text(reason_obj, key) -> str`; `shutdown_temp(reason_obj) -> float`; `availability_online(payload) -> bool`; `offline_numeric_gas() -> list[str]` — GA куда писать −1 при LWT offline: `35/1/2`,`35/1/3`,`35/1/4`,`35/1/7`,`35/1/8`,`35/1/9`,`35/1/10`,`35/1/11`,`35/1/12`,`35/1/13`,`35/1/18`.

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/unit/test_ai_srv_mapping.py
from cottage_monitoring.ai_srv_mapping import (
    availability_online,
    bytes_to_gib,
    load_catalog,
    mib_to_gib,
    numeric_or_sentinel,
    offline_numeric_gas,
    sensor_loss_or_sentinel,
    shutdown_temp,
    shutdown_text,
    text_or_unknown,
)


def test_catalog_has_19_objects_and_prefix() -> None:
    cat = load_catalog()
    assert len(cat) == 19
    gas = [o["ga"] for o in cat]
    assert gas[0] == "35/1/1"
    assert gas[-1] == "35/1/19"
    assert gas == [f"35/1/{i}" for i in range(1, 20)]
    for o in cat:
        assert o["name"].startswith("AI-SRV - ")
        assert o["tags"] == "monitoring, gpu, ai-srv"


def test_numeric_fresh_and_sentinel() -> None:
    assert numeric_or_sentinel(52.0, "fresh") == 52.0
    assert numeric_or_sentinel(52.0, "unknown") == -1
    assert numeric_or_sentinel(None, "fresh") == -1
    assert numeric_or_sentinel(0, "fresh") == 0


def test_sensor_loss_null_is_zero() -> None:
    assert sensor_loss_or_sentinel(None) == 0
    assert sensor_loss_or_sentinel(12.5) == 12.5


def test_conversions() -> None:
    assert mib_to_gib(65536, "fresh") == 64.0
    assert mib_to_gib(None, "fresh") == -1
    assert abs(bytes_to_gib(1073741824, "fresh") - 1.0) < 1e-9


def test_text_and_shutdown() -> None:
    assert text_or_unknown(None) == "unknown"
    assert text_or_unknown("connected") == "connected"
    assert shutdown_text(None, "reason") == "none"
    assert shutdown_text({"reason": "overheat"}, "reason") == "overheat"
    assert shutdown_temp(None) == -1
    assert shutdown_temp({"last_temperature_c": 84}) == 84


def test_availability_and_offline_gas() -> None:
    assert availability_online("online") is True
    assert availability_online("offline") is False
    assert availability_online(b"online") is True
    gas = offline_numeric_gas()
    assert "35/1/1" not in gas
    assert "35/1/14" not in gas
    assert "35/1/15" not in gas
    assert "35/1/2" in gas
    assert "35/1/18" in gas
```

```python
# server/tests/unit/test_object_resolver.py — добавить

def test_ai_srv_temp_is_not_climate_or_heating_diag() -> None:
    o = _obj("35/1/2", "AI-SRV - температура", "monitoring, gpu, ai-srv")
    assert classify_object(o) == ObjectRole.OTHER
    heat = _obj("34/1/6", "Средняя загрузка за 1 мин", "monitoring")
    assert classify_object(heat) == ObjectRole.HEATING_DIAG
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/unit/test_ai_srv_mapping.py tests/unit/test_object_resolver.py::test_ai_srv_temp_is_not_climate_or_heating_diag -v`

Expected: FAIL import `ai_srv_mapping` / missing test.

- [ ] **Step 3: Write catalog JSON and mapping module**

`cm-client/scripts/ai_srv_catalog.json` — массив из 19 объектов. Поля каждого: `ga`, `name`, `mqtt`, `dpt` (`1.001` / `9` / `9.001` / `255`), `kind` (`bool` / `numeric` / `text` / `shutdown_text` / `shutdown_temp`), `tags` всегда `"monitoring, gpu, ai-srv"`. Имена и mqtt как в спеке §7.

```python
# server/src/cottage_monitoring/ai_srv_mapping.py
from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
CATALOG_PATH = _REPO / "cm-client" / "scripts" / "ai_srv_catalog.json"

SENTINEL_NUM = -1.0
UNKNOWN = "unknown"
NONE = "none"

_OFFLINE_NUMERIC = (
    "35/1/2", "35/1/3", "35/1/4", "35/1/7", "35/1/8",
    "35/1/9", "35/1/10", "35/1/11", "35/1/12", "35/1/13", "35/1/18",
)


def load_catalog() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def numeric_or_sentinel(value, status=None) -> float:
    if status is not None and status != "fresh":
        return SENTINEL_NUM
    if value is None:
        return SENTINEL_NUM
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return SENTINEL_NUM
    return float(value)


def sensor_loss_or_sentinel(value) -> float:
    if value is None:
        return 0.0
    return numeric_or_sentinel(value, "fresh")


def mib_to_gib(value, status=None) -> float:
    n = numeric_or_sentinel(value, status)
    if n < 0:
        return SENTINEL_NUM
    return n / 1024.0


def bytes_to_gib(value, status=None) -> float:
    n = numeric_or_sentinel(value, status)
    if n < 0:
        return SENTINEL_NUM
    return n / 1073741824.0


def text_or_unknown(value) -> str:
    if value is None or value == "":
        return UNKNOWN
    return str(value)


def shutdown_text(reason_obj, key: str) -> str:
    if not isinstance(reason_obj, dict):
        return NONE
    v = reason_obj.get(key)
    if v is None or v == "":
        return NONE
    return str(v)


def shutdown_temp(reason_obj) -> float:
    if not isinstance(reason_obj, dict):
        return SENTINEL_NUM
    return numeric_or_sentinel(reason_obj.get("last_temperature_c"), "fresh")


def availability_online(payload) -> bool:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "replace")
    return str(payload).strip() == "online"


def offline_numeric_gas() -> list[str]:
    return list(_OFFLINE_NUMERIC)
```

- [ ] **Step 4: Re-run tests**

Run: `cd server && python -m pytest tests/unit/test_ai_srv_mapping.py tests/unit/test_object_resolver.py::test_ai_srv_temp_is_not_climate_or_heating_diag -v && ruff check src/cottage_monitoring/ai_srv_mapping.py tests/unit/test_ai_srv_mapping.py tests/unit/test_object_resolver.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cm-client/scripts/ai_srv_catalog.json \
  server/src/cottage_monitoring/ai_srv_mapping.py \
  server/tests/unit/test_ai_srv_mapping.py \
  server/tests/unit/test_object_resolver.py
git commit -m "$(cat <<'EOF'
Add AI-SRV group-address catalog and sentinel mapping.

Keep GPU host metrics out of climate tags and give tests a single source for 35/1 GAs.
EOF
)"
```

---

### Task 2: LM Lua — create objects and mqtt_listen

**Files:**
- Create: `cm-client/scripts/create-ai-srv-objects.lua`
- Create: `cm-client/scripts/mqtt_listen.lua` (снять живой id 4 с LM, затем добавить AI-SRV)
- Modify: `server/tests/unit/test_ai_srv_mapping.py` (проверка, что Lua содержит все GA)

**Interfaces:**
- Consumes: catalog GAs/names/tags from Task 1
- Produces: `create-ai-srv-objects.lua` calls `grp.create` per object, skips if `grp.find(address)` exists. `mqtt_listen.lua` subscribes to both cooler topics; `apply_ai_srv_json` / availability handler as spec §8.

How to dump live mqtt_listen (before edit), from repo root:

```bash
source secrets/lm.env
# upload tiny .lp that writes scripting.id=4 script to data/cottage-monitoring/mqtt_listen.lua
# FTP get into cm-client/scripts/mqtt_listen.lua
```

If FTP dump fails, use the known live script (Zigbee `statusmap` as of 2026-09-13) already understood: keep every existing `statusmap` entry including teapot `ble-mqtt-bridge/RK-M173S`.

- [ ] **Step 1: Write failing tests that Lua files exist and list every catalog GA**

```python
# append to server/tests/unit/test_ai_srv_mapping.py
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def test_lua_scripts_contain_all_catalog_gas() -> None:
    create = (_REPO.parent / "cm-client/scripts/create-ai-srv-objects.lua").read_text(encoding="utf-8")
    listen = (_REPO.parent / "cm-client/scripts/mqtt_listen.lua").read_text(encoding="utf-8")
    for o in load_catalog():
        assert o["ga"] in create, o["ga"]
        assert o["name"] in create, o["name"]
        assert o["ga"] in listen, o["ga"]
    assert "cooler-arduino/alex-neuro" in listen
    assert "cooler-arduino/alex-neuro/availability" in listen
    assert "mqtt_listen copy" not in listen
```

Note: `parents[2]` from `server/tests/unit` is `server`; `parent` of that is repo. Use:

```python
_REPO = Path(__file__).resolve().parents[3]
```

`server/tests/unit/test_ai_srv_mapping.py` → parents[0]=unit, [1]=tests, [2]=server, [3]=repo.

- [ ] **Step 2: Run test — FAIL missing lua files**

Run: `cd server && python -m pytest tests/unit/test_ai_srv_mapping.py::test_lua_scripts_contain_all_catalog_gas -v`

- [ ] **Step 3: Write `create-ai-srv-objects.lua`**

```lua
-- One-shot. Scripting → User / Event. Not resident.
-- Tags monitoring,gpu,ai-srv. Skip existing addresses.

local TAGS = { 'monitoring', 'gpu', 'ai-srv' }
local COMMENT = 'source: cooler-arduino/alex-neuro'

local objects = {
  { address = '35/1/1',  name = 'AI-SRV - online',              datatype = 1 },
  { address = '35/1/2',  name = 'AI-SRV - температура',         datatype = 9 },
  { address = '35/1/3',  name = 'AI-SRV - RPM',                 datatype = 9 },
  { address = '35/1/4',  name = 'AI-SRV - PWM',                 datatype = 9 },
  { address = '35/1/5',  name = 'AI-SRV - serial',              datatype = 255 },
  { address = '35/1/6',  name = 'AI-SRV - защита',              datatype = 255 },
  { address = '35/1/7',  name = 'AI-SRV - потеря датчика с',    datatype = 9 },
  { address = '35/1/8',  name = 'AI-SRV - GPU %',               datatype = 9 },
  { address = '35/1/9',  name = 'AI-SRV - VRAM GiB',            datatype = 9 },
  { address = '35/1/10', name = 'AI-SRV - мощность Вт',         datatype = 9 },
  { address = '35/1/11', name = 'AI-SRV - CPU %',               datatype = 9 },
  { address = '35/1/12', name = 'AI-SRV - RAM GiB',             datatype = 9 },
  { address = '35/1/13', name = 'AI-SRV - диск %',              datatype = 9 },
  { address = '35/1/14', name = 'AI-SRV - boot id',             datatype = 255 },
  { address = '35/1/15', name = 'AI-SRV - авария причина',      datatype = 255 },
  { address = '35/1/16', name = 'AI-SRV - авария id',           datatype = 255 },
  { address = '35/1/17', name = 'AI-SRV - авария статус',       datatype = 255 },
  { address = '35/1/18', name = 'AI-SRV - авария температура',  datatype = 9 },
  { address = '35/1/19', name = 'AI-SRV - авария время',        datatype = 255 },
}

for _, o in ipairs(objects) do
  local existing = grp.find(o.address)
  if existing then
    log('create-ai-srv: skip ' .. o.address)
  else
    grp.create({
      address = o.address,
      name = o.name,
      datatype = o.datatype,
      tags = TAGS,
      comment = COMMENT,
    })
    log('create-ai-srv: created ' .. o.address .. ' ' .. o.name)
  end
end
```

LM `grp.find` may be `grp.alias` or lookup by address via `grp.getvalue` — if `grp.find` is nil on this firmware, use:

```lua
local function exists(addr)
  local ok, val = pcall(function() return grp.find(addr) end)
  if ok and val then return true end
  for _, obj in ipairs(grp.all() or {}) do
    if obj.address == addr then return true end
  end
  return false
end
```

- [ ] **Step 4: Write `mqtt_listen.lua`**

Dump live id 4 first. Then add **before** `statusmap` close (new keys):

```lua
['cooler-arduino/alex-neuro'] = 'ai_srv_json',
['cooler-arduino/alex-neuro/availability'] = 'ai_srv_avail',
```

Add helpers (Lua 5.1, no `goto`):

```lua
local function ai_num(v, status)
  if status ~= nil and status ~= 'fresh' then return -1 end
  if v == nil then return -1 end
  if type(v) ~= 'number' then return -1 end
  return v
end

local function ai_mib_gib(v, status)
  local n = ai_num(v, status)
  if n < 0 then return -1 end
  return n / 1024
end

local function ai_bytes_gib(v, status)
  local n = ai_num(v, status)
  if n < 0 then return -1 end
  return n / 1073741824
end

local function apply_ai_srv_offline_numerics()
  local gas = {
    '35/1/2','35/1/3','35/1/4','35/1/7','35/1/8',
    '35/1/9','35/1/10','35/1/11','35/1/12','35/1/13','35/1/18',
  }
  for i = 1, #gas do
    grp.update(gas[i], -1)
  end
end

local function apply_ai_srv_json(dd)
  if not dd then
    apply_ai_srv_offline_numerics()
    return
  end
  grp.update('35/1/2', ai_num(dd.temperature, dd.temperature_status))
  grp.update('35/1/3', ai_num(dd.rpm, dd.rpm_status))
  grp.update('35/1/4', ai_num(dd.pwm, nil))
  if dd.serial_state == nil or dd.serial_state == '' then
    grp.update('35/1/5', 'unknown')
  else
    grp.update('35/1/5', dd.serial_state)
  end
  if dd.protection_state == nil or dd.protection_state == '' then
    grp.update('35/1/6', 'unknown')
  else
    grp.update('35/1/6', dd.protection_state)
  end
  if dd.sensor_loss_elapsed_seconds == nil then
    grp.update('35/1/7', 0)
  else
    grp.update('35/1/7', ai_num(dd.sensor_loss_elapsed_seconds, nil))
  end
  grp.update('35/1/8', ai_num(dd.gpu_utilization_percent, dd.gpu_utilization_percent_status))
  grp.update('35/1/9', ai_mib_gib(dd.gpu_memory_used_mib, dd.gpu_memory_used_mib_status))
  grp.update('35/1/10', ai_num(dd.gpu_power_draw_w, dd.gpu_power_draw_w_status))
  grp.update('35/1/11', ai_num(dd.cpu_utilization_percent, dd.cpu_utilization_percent_status))
  grp.update('35/1/12', ai_bytes_gib(dd.ram_used_bytes, dd.ram_used_bytes_status))
  grp.update('35/1/13', ai_num(dd.disk_used_percent, dd.disk_used_percent_status))
  if dd.boot_id == nil or dd.boot_id == '' then
    grp.update('35/1/14', 'unknown')
  else
    grp.update('35/1/14', dd.boot_id)
  end
  local rs = dd.last_shutdown_reason
  if type(rs) ~= 'table' then
    grp.update('35/1/15', 'none')
    grp.update('35/1/16', 'none')
    grp.update('35/1/17', 'none')
    grp.update('35/1/18', -1)
    grp.update('35/1/19', 'none')
  else
    grp.update('35/1/15', rs.reason or 'none')
    grp.update('35/1/16', rs.event_id or 'none')
    grp.update('35/1/17', rs.status or 'none')
    grp.update('35/1/18', ai_num(rs.last_temperature_c, nil))
    grp.update('35/1/19', rs.timestamp_utc or 'none')
  end
end
```

In `ON_MESSAGE`, **before** generic `statusmap[topic]` JSON loop:

```lua
if topic == 'cooler-arduino/alex-neuro/availability' then
  local online = (data == 'online')
  grp.update('35/1/1', online)
  if not online then apply_ai_srv_offline_numerics() end
  return
end
if topic == 'cooler-arduino/alex-neuro' then
  apply_ai_srv_json(json.pdecode(data))
  return
end
```

Keep `mclient:loop_forever()`, credentials, host `127.0.0.1`. Do not log passwords.

- [ ] **Step 5: Re-run tests + commit**

Run: `cd server && python -m pytest tests/unit/test_ai_srv_mapping.py -v`

```bash
git add cm-client/scripts/create-ai-srv-objects.lua \
  cm-client/scripts/mqtt_listen.lua \
  server/tests/unit/test_ai_srv_mapping.py
git commit -m "$(cat <<'EOF'
Map cooler-arduino MQTT into AI-SRV group addresses on Logic Machine.

Resident mqtt_listen stays the single JSON subscriber; create script is one-shot grp.create.
EOF
)"
```

---

### Task 3: Grafana dashboard

**Files:**
- Modify: `server/deploy/grafana/generate_dashboards.py` (`DASH_LINKS`, `NAV_MD`, `ai_srv()`, `main`)
- Create (generated): `server/deploy/grafana/dashboards/cottage_ai_srv.json`
- Modify: `server/deploy/grafana/README.md`
- Create: `server/tests/unit/test_grafana_ai_srv.py`

**Interfaces:**
- Consumes: catalog GAs
- Produces: dashboard UID `cottage-ai-srv`, title `Cottage — AI-SRV`, tags `cottage, gpu, ai-srv`, refresh `30s`. Nav includes AI-SRV on every Cottage dashboard.

- [ ] **Step 1: Failing test**

```python
# server/tests/unit/test_grafana_ai_srv.py
import json
from pathlib import Path

def test_generated_ai_srv_dashboard_contains_gas() -> None:
    gen = Path(__file__).resolve().parents[2] / "deploy/grafana/generate_dashboards.py"
    ns: dict = {}
    exec(gen.read_text(encoding="utf-8"), ns)
    dash = ns["ai_srv"]()
    blob = json.dumps(dash)
    assert dash["uid"] == "cottage-ai-srv"
    assert "35/1/2" in blob
    assert "35/1/1" in blob
    assert any(l.get("url") == "/grafana/d/cottage-ai-srv/" for l in ns["DASH_LINKS"])
```

`exec` of generate_dashboards may be heavy; prefer:

```python
import importlib.util
spec = importlib.util.spec_from_file_location("gd", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
```

If `ai_srv` missing — FAIL.

- [ ] **Step 2: Run test FAIL**

`cd server && python -m pytest tests/unit/test_grafana_ai_srv.py -v`

- [ ] **Step 3: Implement dashboard**

Add to `DASH_LINKS` after LM Load:

```python
    {
        "title": "AI-SRV",
        "type": "link",
        "url": "/grafana/d/cottage-ai-srv/",
        "icon": "monitor",
        "keepTime": True,
        "targetBlank": False,
    },
```

Append to `NAV_MD`: ` · [AI-SRV](/grafana/d/cottage-ai-srv/)`

Copy SQL helpers from `lm_load`: `_load_latest_sql(ga)` already exists. Add `ai_srv()`:

- nav_panel + row «Сейчас»: stat online (`35/1/1` via BOOL01), temp `35/1/2`, rpm `35/1/3`, pwm `35/1/4`, text/stat serial `35/1/5` and protection `35/1/6` using `e.value #>> '{}'` as string last row
- timeseries temp+rpm+pwm; timeseries GPU% / VRAM / W; timeseries CPU / RAM / disk
- row авария: stats from current_state for `35/1/15`–`19`
- temperature timeseries: threshold line 84
- `insertNulls` as other charts; do not drop −1

For string last-value SQL:

```sql
SELECT e.ts AS time, e.value #>> '{}' AS value
FROM events e
WHERE e.house_id = 'house' AND e.ga = '35/1/5'
ORDER BY e.ts DESC LIMIT 1
```

Register in `main()`: `("cottage_ai_srv.json", ai_srv)`.

Run `python3 server/deploy/grafana/generate_dashboards.py` and commit the JSON.

README: table row UID `cottage-ai-srv`, URL `/grafana/d/cottage-ai-srv/`.

- [ ] **Step 4: Tests + generate + ruff**

`cd server && python -m pytest tests/unit/test_grafana_ai_srv.py -v && ruff check deploy/grafana/generate_dashboards.py tests/unit/test_grafana_ai_srv.py`

- [ ] **Step 5: Commit**

```bash
git add server/deploy/grafana/generate_dashboards.py \
  server/deploy/grafana/dashboards/cottage_ai_srv.json \
  server/deploy/grafana/dashboards/cottage_*.json \
  server/deploy/grafana/README.md \
  server/tests/unit/test_grafana_ai_srv.py
git commit -m "$(cat <<'EOF'
Add Cottage Grafana dashboard for AI-SRV GPU host metrics.

Surface 35/1 group addresses next to existing house dashboards.
EOF
)"
```

Other `cottage_*.json` change because NAV_MD/DASH_LINKS — include them.

---

### Task 4: Specs + deploy LM and Grafana

**Files:**
- Modify: `specs/001-server-mqtt-ingestor/quickstart.md` (Grafana table)
- Modify: `specs/002-logicmachine-mqtt-client/quickstart.md` (AI-SRV scripts)
- Modify: `docs/superpowers/specs/2026-09-13-ai-srv-gpu-monitoring-design.md` status after live

**Interfaces:**
- Consumes: scripts from Task 2, dashboards from Task 3
- Produces: objects on LM; resident 4 running new script; Grafana provisioned on elion

- [ ] **Step 1: Update spec docs (no test)**

001 Grafana list: add `cottage-ai-srv`.  
002: paragraph that user-scripts `create-ai-srv-objects.lua` and resident `mqtt_listen` live in `cm-client/scripts/`; MQTT `cooler-arduino/alex-neuro` is LAN, not `cm/house`.

- [ ] **Step 2: Create objects on LM**

FTP `create-ai-srv-objects.lua` to `data/cottage-monitoring/`, `.lp` that `dofile` or `loadfile` + run, curl with admin+Referer. Confirm `grp` has `35/1/1`.

- [ ] **Step 3: Update scripting id 4 and restart resident**

Same pattern as `deploy/lm-watchdog-update.sh` but `ID=4` and source `cm-client/scripts/mqtt_listen.lua`. Find PID: `ps w | grep scripting-resident`. Restart that resident id (not 73). If SSH `lm_estate` fails, try `ssh -i ~/.ssh/id_ed25519_lm_estate root@192.168.100.130`. After restart, LM log should show mqtt connect; `35/1/2` not stuck at nil if cooler-mqtt is online.

- [ ] **Step 4: Deploy Grafana**

`./server/deploy/grafana/deploy.sh`

Verify: `https://elion.black-castle.ru/grafana/d/cottage-ai-srv/` loads; SQL returns rows within 2 minutes if LM published.

- [ ] **Step 5: Mark spec Implemented + commit docs**

```bash
git add specs/001-server-mqtt-ingestor/quickstart.md \
  specs/002-logicmachine-mqtt-client/quickstart.md \
  docs/superpowers/specs/2026-09-13-ai-srv-gpu-monitoring-design.md
git commit -m "$(cat <<'EOF'
Document AI-SRV LM mapping and Grafana dashboard after live deploy.

Keep operational notes next to the MQTT client and Grafana quickstarts.
EOF
)"
```

If live deploy blocked (no SSH), commit docs as «scripts ready, deploy pending» and report BLOCKED with what ran.

---

## Self-review (plan vs spec)

| Spec § | Task |
|--------|------|
| 19 GA, names, tags, 35/1 | 1, 2 |
| sentinels, sensor_loss 0, LWT −1 numerics | 1, 2 |
| mqtt_listen id 4, two topics, nested shutdown | 2 |
| Grafana cottage-ai-srv, nav | 3 |
| Deploy LM + elion | 4 |
| Non-goals HA/Ops/cooler-arduino | none (not implemented) |
