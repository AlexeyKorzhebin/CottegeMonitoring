# LM Telemetry Holes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking. Do not offer inline execution. Do not use `inherit` for subagent models; pick from `.cursor/rules/subagent-models.mdc`.

**Goal:** LogicMachine object values and cloud `current_state` stay in sync: do not silently drop light status, do not flood the bus from AI-SRV/Zigbee repeats, heal drift with periodic + manual snapshot.

**Architecture:** Cut the flood at the source (`mqtt_listen`: `grp.checkupdate` + 15s min interval for AI-SRV). Make the cottage-monitoring daemon lossless for lights (no `event_sleep` in the handler, `groupresponse`, `force_export`, `snapshot_interval=300`, drop counters). Grafana still reads status `1/2/*` — do not switch tiles to control.

**Tech Stack:** Lua 5.1 on LogicMachine (`grp`, `localbus`, `mosquitto`, `storage`, `config`); Python 3.12 pytest (source-contract tests); deploy via `deploy-lftp.sh` + `lm-apps.sh` + resident id=4 update.

**Incident (2026-09-14):** LM `grp` kitchen/hall `1/2/7`,`1/2/3` = false; cloud `current_state` still true from 13.09 19:20–19:35. Cabinet toggles mostly missing. AI-SRV `35/1/*` ~5500 events/h from 13.09 17:00; meter events fell ~2700→650/h. Daemon `snapshot_interval=0`, `force_export` unread, handler `event_sleep=0.03`, only `groupwrite`.

---

## Global Constraints

- Status `1/2/*` remains the source of truth for lights (Grafana, `list_lights`, skip_unchanged). Do not change dashboards to control `1/1/*`.
- Lua 5.1: no `goto` needed; never `ok and v or nil` for bools (`safe_getvalue` stays).
- `mqtt_listen` **id 4** only. Do not touch `mqtt_listen copy` id 48.
- AI-SRV MQTT topics unchanged: `cooler-arduino/alex-neuro` and `.../availability`. Catalog GAs `35/1/1`–`35/1/19` unchanged.
- Availability / offline (`35/1/1` and `apply_ai_srv_offline_numerics`) MUST write immediately (`force`, no 15s wait).
- AI-SRV numeric/text telemetry: skip unchanged; if changed, at most once per **15** seconds per GA (`AI_SRV_MIN_INTERVAL = 15`).
- Zigbee/relay `statusmap` keys stay; replace `grp.update` with `grp.checkupdate` so repeated OFF does not hit localbus.
- Daemon version string **`1.1.4`**.
- New daemon defaults: `event_sleep=0`, `throttle=0`, `snapshot_interval=300`. Keep `batch_interval=1.5`, `batch_max_size=50`, `loop_sleep=0.25`.
- Throttle, if operator sets `>0`, MUST increment a drop counter and publish it in `status/health`; never silent.
- `force_export` (set by `export_mqtt.lp`) MUST call `publish_meta` and clear the flag.
- localbus: handle **`groupwrite` and `groupresponse`** with the same enqueue path. Do not handle `groupread`.
- Tests: `cd server && python -m pytest <path> -v` then `ruff check` on touched Python. TDD: failing source-contract tests first.
- Do not commit `investor-pitch/`, `docs/architecture/`, `secrets/`, or unrelated Grafana WIP.
- Commit each task. English why-first messages, repo style.
- Do not SSH/FTP deploy in tasks 1–4. Deploy is a follow-up after the branch is green.

---

## File map

| Path | Role |
|------|------|
| `cm-client/scripts/mqtt_listen.lua` | `checkupdate` + AI-SRV 15s gate |
| `server/tests/unit/test_ai_srv_mapping.py` | source contracts for listen.lua |
| `cm-client/daemon/daemon.lua` | holes: response, snapshot, export, sleep, counters |
| `server/tests/unit/test_daemon_lua.py` | source contracts for daemon.lua |
| `cm-client/apply_lowload.lp` | heal profile, not the old drop-lights profile |
| `cm-client/index.lp`, `cm-client/config.lp` | defaults + lowload button |
| `cm-client/health_get.lp` | expose drop/snapshot counters |
| `cm-client/README.md` | config table |
| `specs/002-logicmachine-mqtt-client/contracts/config-schema.md` | defaults |
| `specs/002-logicmachine-mqtt-client/research.md` | R-028 |
| `specs/002-logicmachine-mqtt-client/quickstart.md` | operational |
| `specs/001-server-mqtt-ingestor/quickstart.md` | one line: lights follow LM snapshot |
| `cm-client/export_mqtt.lp` | unchanged contract; daemon must honor it |

---

### Task 1: mqtt_listen — checkupdate + AI-SRV interval

**Files:**
- Modify: `cm-client/scripts/mqtt_listen.lua`
- Test: `server/tests/unit/test_ai_srv_mapping.py`

**Interfaces:**
- Consumes: existing `apply_ai_srv_json` / `apply_ai_srv_offline_numerics` / `statusmap`
- Produces: `AI_SRV_MIN_INTERVAL = 15`; `knx_check(ga, value)`; `ai_knx(ga, value, force)` used by AI-SRV path; zigbee/json path uses `knx_check`

- [ ] **Step 1: Write failing tests** (append to `test_ai_srv_mapping.py`)

```python
def test_mqtt_listen_uses_checkupdate_not_unconditional_update() -> None:
    listen = (_REPO / "cm-client/scripts/mqtt_listen.lua").read_text(encoding="utf-8")
    assert "grp.checkupdate" in listen
    assert "AI_SRV_MIN_INTERVAL" in listen
    assert "AI_SRV_MIN_INTERVAL = 15" in listen
    # Zigbee / AI-SRV must not hammer localbus on identical values
    assert listen.count("grp.update(") == 0


def test_mqtt_listen_ai_srv_force_path_exists() -> None:
    listen = (_REPO / "cm-client/scripts/mqtt_listen.lua").read_text(encoding="utf-8")
    assert "ai_knx" in listen
    assert "force" in listen
    assert "apply_ai_srv_offline_numerics" in listen
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd server && python -m pytest tests/unit/test_ai_srv_mapping.py -v
```

Expected: new tests fail (`grp.checkupdate` / `AI_SRV_MIN_INTERVAL` missing). Existing tests still pass.

- [ ] **Step 3: Implement mqtt_listen helpers and call sites**

Near the top of `mqtt_listen.lua` (after `OnOff2Bool`), add:

```lua
local AI_SRV_MIN_INTERVAL = 15
local ai_last = {}

local function knx_check(ga, value)
  grp.checkupdate(ga, value)
end

-- force=true: availability / offline, skip interval.
local function ai_knx(ga, value, force)
  local now = os.time()
  local prev = ai_last[ga]
  if not force then
    if prev and prev.v == value then
      return
    end
    if prev and (now - prev.t) < AI_SRV_MIN_INTERVAL then
      return
    end
  end
  ai_last[ga] = { v = value, t = now }
  knx_check(ga, value)
end
```

Replace every `grp.update('35/1/…'` inside `apply_ai_srv_json` with `ai_knx('35/1/…', …)`.

In `apply_ai_srv_offline_numerics` use `ai_knx(gas[i], -1, true)`.

Availability:

```lua
ai_knx('35/1/1', online, true)
if not online then apply_ai_srv_offline_numerics() end
```

In `ON_MESSAGE` json/zigbee branch replace `grp.update(address.addr, …)` and `grp.update(address, v)` with `knx_check(...)`. Keep existing `grp.checkupdate(obj, value)` for raw DRM88 strings.

Do not change `statusmap` keys or AI-SRV topics.

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd server && python -m pytest tests/unit/test_ai_srv_mapping.py -v && ruff check tests/unit/test_ai_srv_mapping.py
```

- [ ] **Step 5: Commit**

```bash
git add cm-client/scripts/mqtt_listen.lua server/tests/unit/test_ai_srv_mapping.py
git commit -m "$(cat <<'EOF'
Stop AI-SRV and Zigbee repeats from flooding the KNX localbus.

Unconditional grp.update was generating thousands of groupwrites per hour and starving light status.
EOF
)"
```

---

### Task 2: daemon 1.1.4 — do not drop lights, heal snapshot

**Files:**
- Modify: `cm-client/daemon/daemon.lua`
- Create: `server/tests/unit/test_daemon_lua.py`

**Interfaces:**
- Consumes: `publish_meta()`, `flush_batch()`, `safe_getvalue()`, config keys
- Produces: version `1.1.4`; `handle_bus_event(event, ev_type)`; `groupwrite` + `groupresponse`; `force_export`; `snapshot_interval`; drop counters `S.dropped_throttle`, `S.dropped_nofind`; health JSON fields `dropped_throttle`, `dropped_nofind`, `last_snapshot_ts`, `event_sleep`, `throttle`, `snapshot_interval`

- [ ] **Step 1: Write failing tests** (`server/tests/unit/test_daemon_lua.py`)

```python
from pathlib import Path

_DAEMON = Path(__file__).resolve().parents[3] / "cm-client/daemon/daemon.lua"


def _src() -> str:
    return _DAEMON.read_text(encoding="utf-8")


def test_version_114() -> None:
    assert "1.1.4" in _src()


def test_listens_groupresponse_and_groupwrite() -> None:
    src = _src()
    assert "sethandler('groupwrite'" in src
    assert "sethandler('groupresponse'" in src
    assert "sethandler('groupread'" not in src


def test_force_export_and_snapshot_interval() -> None:
    src = _src()
    assert "force_export" in src
    assert "snapshot_interval" in src
    assert "cfg('snapshot_interval', 300)" in src or 'cfg("snapshot_interval", 300)' in src
    assert "cfg('event_sleep', 0)" in src or 'cfg("event_sleep", 0)' in src
    assert "cfg('throttle', 0)" in src or 'cfg("throttle", 0)' in src


def test_handler_does_not_sleep() -> None:
    src = _src()
    # event_sleep may still exist as config but must not os.sleep inside handle_bus_event
    start = src.find("local function handle_bus_event")
    assert start != -1
    rest = src[start:]
    end = rest.find("\nlb:sethandler")
    body = rest[:end]
    assert "os.sleep" not in body


def test_throttle_drop_is_counted() -> None:
    src = _src()
    assert "dropped_throttle" in src
    assert "dropped_nofind" in src
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd server && python -m pytest tests/unit/test_daemon_lua.py -v
```

- [ ] **Step 3: Implement daemon.lua**

Bump header comment to `v1.1.4`. Change `storage.set('cm_boot', 'v113_start')` to `'v114_start'`.

Config block:

```lua
  throttle = tonumber(cfg('throttle', 0)) or 0,
  event_sleep = tonumber(cfg('event_sleep', 0)) or 0,
  snapshot_interval = tonumber(cfg('snapshot_interval', 300)) or 300,
```

Keep reading `event_sleep` for health visibility but **do not call `os.sleep` in the bus handler** (ignore the value for sleeping; operators must not be able to re-enable handler sleep via config — that was the miss hole).

`S` add:

```lua
  dropped_throttle = 0,
  dropped_nofind = 0,
  last_snapshot_ts = 0,
```

Replace the single `lb:sethandler('groupwrite', …)` with:

```lua
local function find_bus_obj(event)
  local dst = event.dst or event.dstraw
  local obj = grp.find(dst)
  if obj then return obj, dst end
  if event.dstraw ~= nil and event.dstraw ~= dst then
    obj = grp.find(event.dstraw)
    if obj then return obj, event.dstraw end
  end
  if event.dst ~= nil and event.dst ~= dst then
    obj = grp.find(event.dst)
    if obj then return obj, event.dst end
  end
  return nil, dst
end

local function handle_bus_event(event, ev_type)
  if C.throttle > 0 then
    local now = os.time()
    if now ~= S.last_evt_ts then S.last_evt_ts = now; S.evt_count = 0 end
    S.evt_count = S.evt_count + 1
    if S.evt_count > C.throttle then
      S.dropped_throttle = S.dropped_throttle + 1
      return
    end
  end
  local obj, dst = find_bus_obj(event)
  if not obj then
    S.dropped_nofind = S.dropped_nofind + 1
    return
  end
  local val = event.value
  if val == nil then val = safe_getvalue(dst) end
  local ts = os.time()
  S.seq = S.seq + 1
  S.last_event_ts = ts
  local ga = obj.address or dst
  local ga_safe = tostring(ga):gsub('/', '-')
  local evt = {
    ts = ts, seq = S.seq, type = ev_type, ga = ga,
    id = obj.id, name = obj.name, datatype = obj.datatype or 0, value = val,
  }
  local state = { ts = ts, value = val, datatype = obj.datatype or 0 }
  if C.batch_interval > 0 then
    table.insert(event_batch, { evt = evt, ga_safe = ga_safe, state = state })
    if C.batch_max_size > 0 and #event_batch >= C.batch_max_size then
      flush_batch()
    end
  else
    do_pub('events', json.encode(evt), 0, false)
    do_pub('state/ga/' .. ga_safe, json.encode(state), 1, true)
  end
end

lb:sethandler('groupwrite', function(event)
  handle_bus_event(event, 'knx.groupwrite')
end)
lb:sethandler('groupresponse', function(event)
  handle_bus_event(event, 'knx.groupresponse')
end)
```

After successful `publish_meta()`, set `S.last_snapshot_ts = os.time()`.

Main loop additions (inside the connected section, after `lb:step` / batch flush):

```lua
    if storage.get('force_export') then
      pcall(storage.set, 'force_export', nil)
      pcall(publish_meta)
    end
    if S.connected and C.snapshot_interval > 0 then
      local now = os.time()
      if S.last_snapshot_ts == 0 then
        -- wait for first ON_CONNECT publish_meta
      elseif (now - S.last_snapshot_ts) >= C.snapshot_interval then
        pcall(publish_meta)
      end
    end
```

First connect already calls `publish_meta` via `S.meta_sent`. Ensure that path sets `last_snapshot_ts`.

Health publish JSON add:

```lua
        dropped_throttle = S.dropped_throttle,
        dropped_nofind = S.dropped_nofind,
        last_snapshot_ts = S.last_snapshot_ts,
        snapshot_interval = C.snapshot_interval,
        throttle = C.throttle,
```

Also persist counters occasionally in `hb()`:

```lua
  pcall(storage.set, 'cm_dropped_throttle', S.dropped_throttle)
  pcall(storage.set, 'cm_dropped_nofind', S.dropped_nofind)
  pcall(storage.set, 'cm_last_snapshot_ts', S.last_snapshot_ts)
```

Keep piggyback rate: only write these when values changed, same pattern as `last_event_ts`.

Online status version: `'1.1.4'`.

- [ ] **Step 4: Tests PASS**

```bash
cd server && python -m pytest tests/unit/test_daemon_lua.py -v && ruff check tests/unit/test_daemon_lua.py
```

- [ ] **Step 5: Commit**

```bash
git add cm-client/daemon/daemon.lua server/tests/unit/test_daemon_lua.py
git commit -m "$(cat <<'EOF'
Heal LM→cloud drift: snapshot, groupresponse, and counted drops.

Silent throttle/sleep and unread force_export left Grafana showing stale light status.
EOF
)"
```

---

### Task 3: config defaults, lowload profile, health JSON

**Files:**
- Modify: `cm-client/apply_lowload.lp`
- Modify: `cm-client/index.lp`
- Modify: `cm-client/config.lp`
- Modify: `cm-client/health_get.lp`
- Modify: `server/tests/unit/test_daemon_lua.py` (add UI/lp source contracts) **or** new `server/tests/unit/test_lm_config_defaults.py`

**Interfaces:**
- Consumes: Task 2 storage keys `cm_dropped_throttle`, `cm_dropped_nofind`, `cm_last_snapshot_ts`
- Produces: lowload/heal profile: `throttle=0`, `event_sleep=0`, `snapshot_interval=300`, `loop_sleep=0.25`, `batch_interval=1.5`, `batch_max_size=50`

- [ ] **Step 1: Failing tests** in `server/tests/unit/test_lm_config_defaults.py`

```python
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def test_apply_lowload_is_heal_profile() -> None:
    src = (_ROOT / "cm-client/apply_lowload.lp").read_text(encoding="utf-8")
    assert "snapshot_interval" in src
    assert "300" in src
    assert "event_sleep" in src
    # must not re-enable handler sleep / light-dropping throttle
    assert "throttle', 20" not in src and 'throttle", 20' not in src
    assert "event_sleep', 0.03" not in src and 'event_sleep", 0.03' not in src


def test_index_lowload_button_heal_values() -> None:
    src = (_ROOT / "cm-client/index.lp").read_text(encoding="utf-8")
    assert "-throttle').val(0)" in src or '-throttle").val(0)' in src
    assert "-event_sleep').val(0)" in src or '-event_sleep").val(0)' in src
    assert "-snapshot_interval').val(300)" in src or '-snapshot_interval").val(300)' in src


def test_health_exposes_drop_counters() -> None:
    src = (_ROOT / "cm-client/health_get.lp").read_text(encoding="utf-8")
    assert "cm_dropped_throttle" in src
    assert "cm_dropped_nofind" in src
    assert "cm_last_snapshot_ts" in src
```

- [ ] **Step 2: Run FAIL**

```bash
cd server && python -m pytest tests/unit/test_lm_config_defaults.py -v
```

- [ ] **Step 3: Implement**

`apply_lowload.lp`:

```lua
config.set('cottage-monitoring', 'throttle', 0)
config.set('cottage-monitoring', 'event_sleep', 0)
config.set('cottage-monitoring', 'loop_sleep', 0.25)
config.set('cottage-monitoring', 'batch_interval', 1.5)
config.set('cottage-monitoring', 'batch_max_size', 50)
config.set('cottage-monitoring', 'snapshot_interval', 300)
...
print(json.encode({ ok = true, msg = 'heal: throttle=0, event_sleep=0, snapshot_interval=300, batch=1.5. Restart daemon.' }))
```

`index.lp` button click: set throttle 0, event_sleep 0, snapshot_interval 300, keep batch 1.5 / loop 0.25. Help text: `throttle=0, snapshot=300s, event_sleep=0, batch=1.5s`. Default HTML `value=` on those inputs: snapshot 300, throttle 0, event_sleep 0. JS save fallback: `if (isNaN(throttle)) throttle = 0;` and `event_sleep` default 0.

Same defaults in `config.lp`.

`health_get.lp` add to `out`:

```lua
  dropped_throttle = num('cm_dropped_throttle') or 0,
  dropped_nofind = num('cm_dropped_nofind') or 0,
  last_snapshot_ts = num('cm_last_snapshot_ts'),
```

- [ ] **Step 4: PASS**

```bash
cd server && python -m pytest tests/unit/test_lm_config_defaults.py tests/unit/test_daemon_lua.py -v && ruff check tests/unit/test_lm_config_defaults.py
```

- [ ] **Step 5: Commit**

```bash
git add cm-client/apply_lowload.lp cm-client/index.lp cm-client/config.lp cm-client/health_get.lp server/tests/unit/test_lm_config_defaults.py
git commit -m "$(cat <<'EOF'
Default LM config to snapshot heal instead of dropping groupwrites.

The old lowload profile (throttle=20, event_sleep=0.03) is what hid kitchen/hall OFF.
EOF
)"
```

---

### Task 4: specs and README (R-028)

**Files:**
- Modify: `specs/002-logicmachine-mqtt-client/research.md`
- Modify: `specs/002-logicmachine-mqtt-client/quickstart.md`
- Modify: `specs/002-logicmachine-mqtt-client/contracts/config-schema.md`
- Modify: `specs/001-server-mqtt-ingestor/quickstart.md` (Grafana lights row / operational)
- Modify: `cm-client/README.md`

- [ ] **Step 1: Add R-028 to 002 research.md** after the latest R-xxx, with table row.

Title: **R-028: Stale light status — localbus drops + no snapshot (2026-09-14)**

Facts to record:
- Grafana status `1/2/*` was correct to use; cloud lagged LM `grp`.
- Kitchen `1/2/7` / hall `1/2/3` false on LM, true in `current_state` since 13.09 19:20–19:35.
- AI-SRV `35/1/*` ~5500/h from 13.09 17:00; meter 32/1/* 2700→650/h same hour.
- Holes: `grp.update` flood, `event_sleep` in handler, silent throttle, `force_export` unread, `snapshot_interval=0`, only `groupwrite`.
- Fix: checkupdate+15s AI-SRV; daemon 1.1.4 groupresponse, snapshot 300s, throttle 0, counted drops, force_export.

- [ ] **Step 2: quickstart 002** — config defaults table: snapshot 300, throttle 0, event_sleep 0. Note: after daemon deploy run `apply_lowload.lp` (now heal) + restart; then «Выгрузить в MQTT» or wait ≤300s. Update `mqtt_listen` id=4 the same way as AI-SRV plan (FTP + `db:update` + respawn).

- [ ] **Step 3: config-schema.md** example JSON: `"snapshot_interval": 300`, `"throttle": 0`, `"event_sleep": 0`. Document throttle 0 default.

- [ ] **Step 4: 001 quickstart** Grafana lights: one sentence that instant tiles are `current_state` of status `1/2/*` and a missed groupwrite is healed by LM snapshot (R-028).

- [ ] **Step 5: README** config table match new defaults.

- [ ] **Step 6: Commit**

```bash
git add specs/002-logicmachine-mqtt-client/research.md specs/002-logicmachine-mqtt-client/quickstart.md specs/002-logicmachine-mqtt-client/contracts/config-schema.md specs/001-server-mqtt-ingestor/quickstart.md cm-client/README.md
git commit -m "$(cat <<'EOF'
Document R-028: light tiles lag when LM drops groupwrites.

Operators need snapshot defaults and the mqtt_listen checkupdate rule, not a Grafana control fallback.
EOF
)"
```

---

## Deploy (controller after tasks, not a coded task)

From repo root, after the branch is green:

```bash
./deploy/lm-apps.sh pause-wd
./deploy/lm-apps.sh stop
./deploy/deploy-lftp.sh
# apply heal config
# curl apply_lowload.lp (admin)
./deploy/lm-apps.sh start
./deploy/lm-apps.sh health
# mqtt_listen id=4: same FTP+db:update+respawn pattern as AI-SRV
# then export_mqtt / wait snapshot; confirm kitchen 1/2/7 current_state matches LM
```

Verify: LM export `1/2/3`,`1/2/7` equals Grafana `current_state`; `35/1/*` event rate << 5500/h; health `dropped_throttle` stays 0; cabinet toggle produces `1/2/14` events.

---

## Self-review

- Spec holes from incident: flood source ✅, silent drops ✅, force_export ✅, snapshot ✅, groupresponse ✅, health visibility ✅, docs ✅, Grafana control not used ✅
- No TBD placeholders
- Names: `ai_knx`, `knx_check`, `handle_bus_event`, `AI_SRV_MIN_INTERVAL=15`, version `1.1.4` consistent
