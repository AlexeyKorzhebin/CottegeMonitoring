# HA Energy, Batteries, Grafana Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking. Do not offer inline execution. Do not use `inherit` for subagent models; pick from `.cursor/rules/subagent-models.mdc`.

**Goal:** В семейной витрине HA — шесть энергетических чисел в area «Дом», штатный Energy на счётчике ЖКХ, батареи Zigbee в комнатах и вкладка «Графики» на Grafana SELECT.

**Architecture:** Nord `get_energy_status` не режем (Telegram по-прежнему видит фазы). HA snapshot фильтрует 6 GA. Батареи — второй `get_sensors` с `kind=battery` (роль `room_battery`, как humidity). Grafana не дублируем SQL в Lovelace: iframe или ссылка. Мозг дома — LogicMachine.

**Tech Stack:** Python 3.12 (Nord, pytest, ruff); HA custom component без пакета `homeassistant` в unit-тестах маппера; systemd/nginx на elion; Grafana OSS `allow_embedding`.

**Spec:** `docs/superpowers/specs/2026-08-28-ha-energy-grafana-design.md`

---

## Global Constraints

- Каталог Ops остаётся **17** имён. Новых Ops нет. `get_energy_status` уже в каталоге — только начать звать из HA.
- `ENERGY_SUMMARY_GAS` в Nord **не сужать**. Фазы, Q/S, `32/1/39` остаются для Telegram и Grafana SQL.
- Счётчик ЖКХ в HA — только GA `32/1/59`. Не `32/1/39`.
- Poll HA: **два** новых read-вызова рядом с существующими, не смешивать humidity и battery в одном `kind`.
- `house_id` продакшена: `house`. Ключ HA: `home-assistant`.
- HA не получает KNX, не подписывается на MQTT `cm/#` / `ha/#`. Grafana не пишет команды.
- Анонимный Grafana на весь инстанс запрещён. Если iframe без cookie пустой — ссылка, не anonymous auth.
- Код Nord на elion не `rsync` / `scp` / `git clone`. Образ локально `linux/amd64`. HA-компонент: `./server/deploy/ha-sync-component.sh`.
- `investor-pitch/` и `docs/architecture/` не коммитить.
- Тесты Nord: `cd server && python -m pytest <path> -v`. HA-маппер: `cd ha && python -m pytest tests -v`.
- После Python Nord: `cd server && ruff check .`
- Перед sync HA-компонента на elion **сначала** выкатить Nord с `kind=battery`. Иначе `DiscoverKind("battery")` роняет весь coordinator.
- Версия Nord этой волны: **0.3.4** (`pyproject.toml`, `IMAGE_PIN.yaml`, `cottage-monitoring.service`). Alembic не нужен.
- Коммитить каждую задачу этого плана. Не трогать чужие untracked (investor-pitch, architecture PNG).

---

## File map

| Path | Role |
|------|------|
| `server/src/cottage_monitoring/services/object_resolver.py` | `ObjectRole.ROOM_BATTERY`; classify до generic SENSOR |
| `server/src/cottage_monitoring/services/agent_actions.py` | `get_sensors(kind="battery")` как humidity |
| `server/src/cottage_monitoring/ops/catalog.py` | описание `get_sensors`: humidity + battery |
| `server/tests/unit/test_object_resolver.py` | classify `zb_sensor_*_battery` → `ROOM_BATTERY` |
| `server/tests/unit/test_read_ops_placement.py` | `kind=battery` отдаёт area/floor |
| `ha/custom_components/cottage_monitoring/snapshot.py` | allowlist 6 GA; `get_sensors_battery`; имена; `sensor_ha_profile` |
| `ha/custom_components/cottage_monitoring/coordinator.py` | + `get_energy_status`, + `get_sensors` battery |
| `ha/custom_components/cottage_monitoring/sensor.py` | device_class для energy/battery |
| `ha/tests/test_snapshot.py` | 6 ключей, отброс фаз/`32/1/39`, имена, батарея |
| `server/deploy/ha/configuration.yaml` | Lovelace dashboard «Графики» |
| `server/deploy/ha/dashboards/graphs.yaml` | iframe + fallback-ссылки Grafana |
| `server/deploy/ha/energy-grid.example.json` | шаблон `.storage/energy` |
| `server/deploy/grafana/grafana-embedding.ini.snippet` | `allow_embedding = true` |
| `server/pyproject.toml`, `IMAGE_PIN.yaml`, unit | pin 0.3.4 |
| `specs/001-server-mqtt-ingestor/quickstart.md`, `research.md` | R-027, entity_id, UID, fallback |
| `docs/superpowers/specs/2026-08-28-ha-energy-grafana-design.md` | Implemented после live |
| `docs/superpowers/specs/2026-08-28-ha-nord-design.md` | batteries/energy — follow-up выполнен |

---

### Task 1: Nord — роль `room_battery` и `get_sensors(kind="battery")`

**Files:**
- Modify: `server/src/cottage_monitoring/services/object_resolver.py`
- Modify: `server/src/cottage_monitoring/services/agent_actions.py`
- Modify: `server/src/cottage_monitoring/ops/catalog.py` (строка описания `get_sensors`)
- Test: `server/tests/unit/test_object_resolver.py`
- Test: `server/tests/unit/test_read_ops_placement.py`

**Interfaces:**
- `ObjectRole.ROOM_BATTERY = "room_battery"` рядом с `ROOM_HUMIDITY`.
- `classify_object`: **до** ветки `tagset & {..., "battery"}` → `SENSOR`. Если `"battery" in tagset and "zb_sensor" in tagset` **или** имя (lower) оканчивается на `_battery` и есть `zb_sensor` — `ROOM_BATTERY`.
- `_roles_for_kind(DiscoverKind.SENSOR)` включает `ROOM_BATTERY`.
- `get_sensors(..., kind="battery")` резолвит `DiscoverKind.SENSOR` + `role=ObjectRole.ROOM_BATTERY`, затем `_with_placement` как humidity. **Не** вызывать `DiscoverKind("battery")` — такого kind нет.
- `kind="humidity"` без регрессии. `kind="not-a-kind"` по-прежнему `ValueError`.
- `ENERGY_SUMMARY_GAS` не менять. Каталог 17 имён не менять.

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/unit/test_object_resolver.py — добавить

def test_classify_room_battery_zb() -> None:
    o = _obj("33/1/20", "zb_sensor_fl1_kitchen_battery", "floor1,battery,zb_sensor")
    assert classify_object(o) == ObjectRole.ROOM_BATTERY


def test_classify_battery_not_generic_sensor() -> None:
    o = _obj("33/1/20", "zb_sensor_fl1_bedroom_battery", "floor1,battery,zb_sensor")
    assert classify_object(o) != ObjectRole.SENSOR
```

```python
# server/tests/unit/test_read_ops_placement.py — добавить рядом с humidity

def test_get_sensors_battery_has_placement(monkeypatch) -> None:
    bat = _ro(
        "33/1/20",
        "zb_sensor_fl1_kitchen_battery",
        ["floor1", "battery", "zb_sensor"],
        ObjectRole.ROOM_BATTERY,
    )

    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ok", matches=[bat])

    async def fake_states(*_a, **_k):
        return {"33/1/20": 87}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)

    out = asyncio.run(agent_actions.get_sensors(MagicMock(), "house", kind="battery"))
    assert out["items"][0]["area"] == "кухня"
    assert out["items"][0]["floor"] == "1"
    assert out["items"][0]["value"] == 87
    assert out["items"][0]["role"] == "room_battery"
```

В тесте battery `fake_resolve` должен получить `role=ObjectRole.ROOM_BATTERY`. Если проще не проверять kwargs — достаточно placement items. Для жёсткости:

```python
    captured = {}

    async def fake_resolve(*_a, **kwargs):
        captured.update(kwargs)
        return ResolveResult(status="ok", matches=[bat])
    ...
    assert captured["role"] == ObjectRole.ROOM_BATTERY
    assert captured["kind"] == DiscoverKind.SENSOR
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd server && python -m pytest tests/unit/test_object_resolver.py::test_classify_room_battery_zb tests/unit/test_read_ops_placement.py::test_get_sensors_battery_has_placement -v
```

Expected: FAIL (`ObjectRole.ROOM_BATTERY` отсутствует и/или `DiscoverKind("battery")`).

- [ ] **Step 3: Minimal implementation**

В `object_resolver.py` в `ObjectRole`:

```python
    ROOM_HUMIDITY = "room_humidity"
    ROOM_BATTERY = "room_battery"
```

В `classify_object` сразу после humidity:

```python
    if "humidity" in tagset and "zb_sensor" in tagset:
        return ObjectRole.ROOM_HUMIDITY
    if "zb_sensor" in tagset and ("battery" in tagset or name.endswith("_battery")):
        return ObjectRole.ROOM_BATTERY
```

В `_roles_for_kind` для `DiscoverKind.SENSOR` добавить `ObjectRole.ROOM_BATTERY`.

В `agent_actions.get_sensors`:

```python
    if kind == "humidity":
        result = await resolve_objects(
            session,
            house_id,
            query=query,
            kind=DiscoverKind.SENSOR,
            role=ObjectRole.ROOM_HUMIDITY,
        )
    elif kind == "battery":
        result = await resolve_objects(
            session,
            house_id,
            query=query,
            kind=DiscoverKind.SENSOR,
            role=ObjectRole.ROOM_BATTERY,
        )
    else:
        dk = DiscoverKind(kind) if kind else DiscoverKind.SENSOR
        result = await resolve_objects(session, house_id, query=query, kind=dk)
```

Описание `get_sensors` в catalog: упомянуть `humidity` и `battery` как специальные kind.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd server && python -m pytest tests/unit/test_object_resolver.py tests/unit/test_read_ops_placement.py tests/unit/test_ops_drift.py -v && ruff check src tests
```

Expected: PASS. Drift по-прежнему 17 имён.

- [ ] **Step 5: Commit**

```bash
git add server/src/cottage_monitoring/services/object_resolver.py \
  server/src/cottage_monitoring/services/agent_actions.py \
  server/src/cottage_monitoring/ops/catalog.py \
  server/tests/unit/test_object_resolver.py \
  server/tests/unit/test_read_ops_placement.py
git commit -m "$(cat <<'EOF'
feat: resolve Zigbee batteries via get_sensors kind=battery

HA needs room batteries without pulling PIR/illuminance. Classify zb_sensor battery before the generic SENSOR catch.
EOF
)"
```

---

### Task 2: HA snapshot — 6 energy keys + батареи

**Files:**
- Modify: `ha/custom_components/cottage_monitoring/snapshot.py`
- Test: `ha/tests/test_snapshot.py`

**Interfaces:**
- Константа allowlist (только HA, Nord не трогать):

```python
ENERGY_HA_BY_GA: dict[str, str] = {
    "32/1/35": "power",
    "32/1/7": "frequency",
    "32/1/59": "meter",
    "32/1/57": "hour",
    "32/1/58": "daily",
    "32/1/38": "pf",
}

ENERGY_DISPLAY_NAME: dict[str, str] = {
    "power": "Сейчас",
    "frequency": "Частота",
    "meter": "Счётчик",
    "hour": "За час",
    "daily": "За сутки",
    "pf": "PF",
}
```

- `HouseSnapshot.from_ops` читает `ops["get_energy_status"]["items"]`. Для каждого item с `ga` из allowlist создаёт `SensorItem(name=ENERGY_DISPLAY_NAME[key], kind=key, value=..., area=None, floor=None, unique_id=f"{house_id}:energy:{key}")`. GA вне allowlist (`32/1/39`, фазы, Q/S) отбросить. Нет GA — сущность не создаём.
- `ops["get_sensors"]` по-прежнему **только humidity** (`kind="humidity"`).
- `ops["get_sensors_battery"]` (ключ словаря coordinator, не имя Ops): items → `SensorItem(..., kind="battery", unique_id=_unique_id(house_id, "sensor_battery", name))`.
- `sensor_display_name`: `kind=="battery"` → `"Батарея"`; `kind` в `ENERGY_DISPLAY_NAME` → соответствующее имя.
- Отсутствующие ключи ops = пустой список (старые фикстуры без energy/battery не ломаются).
- `sensor_ha_profile(kind) -> dict` со строками для HA (тестируется без пакета `homeassistant`):

```python
def sensor_ha_profile(kind: str) -> dict[str, str | None]:
    """Keys: device_class, unit, state_class. Values match HA enum *values*."""
    profiles = {
        "power": {"device_class": "power", "unit": "W", "state_class": "measurement"},
        "frequency": {"device_class": "frequency", "unit": "Hz", "state_class": "measurement"},
        "meter": {"device_class": "energy", "unit": "kWh", "state_class": "total_increasing"},
        "hour": {"device_class": "energy", "unit": "kWh", "state_class": "total"},
        "daily": {"device_class": "energy", "unit": "kWh", "state_class": "total"},
        "pf": {"device_class": "power_factor", "unit": None, "state_class": "measurement"},
        "battery": {"device_class": "battery", "unit": "%", "state_class": "measurement"},
        "humidity": {"device_class": "humidity", "unit": "%", "state_class": "measurement"},
        "air": {"device_class": "temperature", "unit": "°C", "state_class": "measurement"},
        "floor": {"device_class": "temperature", "unit": "°C", "state_class": "measurement"},
    }
    return profiles.get(kind, {"device_class": "temperature", "unit": "°C", "state_class": "measurement"})
```

Outdoor остаётся в `_apply_device_class` по label, как сейчас (не обязательно тащить в profile).

- [ ] **Step 1: Write the failing tests**

В `ha/tests/test_snapshot.py` расширить `OPS` **не обязательно** — отдельные тесты со своими ops, чтобы не ломать существующие.

```python
def test_energy_snapshot_keeps_six_keys_drops_phases() -> None:
    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {"items": []},
        "get_climate": {"auto_heating_enabled": False, "zones": []},
        "get_temperature": {"items": []},
        "get_sensors": {"items": []},
        "get_sensors_battery": {"items": []},
        "get_kettle": {},
        "get_energy_status": {
            "items": [
                {"ga": "32/1/35", "name": "Total P", "value": 420, "units": "W"},
                {"ga": "32/1/36", "name": "Total Q", "value": 10, "units": "var"},
                {"ga": "32/1/39", "name": "AP energy", "value": 999, "units": "kWh"},
                {"ga": "32/1/7", "name": "Frequency", "value": 50.02, "units": "Hz"},
                {"ga": "32/1/59", "name": "consumption Total", "value": 1234.5, "units": "kWh"},
                {"ga": "32/1/57", "name": "Hour", "value": 1.2, "units": "kWh"},
                {"ga": "32/1/58", "name": "Daily", "value": 18.0, "units": "kWh"},
                {"ga": "32/1/38", "name": "PF", "value": 0.97, "units": ""},
                {"ga": "32/1/1", "name": "Urms L1", "value": 230, "units": "V"},
            ]
        },
    }
    snap = HouseSnapshot.from_ops("house", ops)
    energy = {s.kind: s for s in snap.sensors if s.kind in {"power", "frequency", "meter", "hour", "daily", "pf"}}
    assert set(energy) == {"power", "frequency", "meter", "hour", "daily", "pf"}
    assert energy["power"].value == 420
    assert energy["meter"].value == 1234.5
    assert energy["meter"].unique_id == "house:energy:meter"
    assert energy["power"].unique_id == "house:energy:power"
    assert all(s.area is None and s.floor is None for s in energy.values())
    from cottage_monitoring.snapshot import sensor_display_name
    assert sensor_display_name(name="ignored", kind="power") == "Сейчас"
    assert sensor_display_name(name="ignored", kind="frequency") == "Частота"
    assert sensor_display_name(name="ignored", kind="meter") == "Счётчик"
    assert sensor_display_name(name="ignored", kind="hour") == "За час"
    assert sensor_display_name(name="ignored", kind="daily") == "За сутки"
    assert sensor_display_name(name="ignored", kind="pf") == "PF"


def test_energy_missing_ga_skips_only_that_key() -> None:
    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {"items": []},
        "get_climate": {"auto_heating_enabled": False, "zones": []},
        "get_temperature": {"items": []},
        "get_sensors": {"items": []},
        "get_kettle": {},
        "get_energy_status": {"items": [{"ga": "32/1/35", "name": "Total P", "value": 1}]},
    }
    snap = HouseSnapshot.from_ops("house", ops)
    kinds = {s.kind for s in snap.sensors}
    assert "power" in kinds
    assert "meter" not in kinds


def test_battery_sensors_and_display_name() -> None:
    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {"items": []},
        "get_climate": {"auto_heating_enabled": False, "zones": []},
        "get_temperature": {"items": []},
        "get_sensors": {
            "items": [
                {"name": "zb_sensor_fl1_living_room_humidity", "value": 44, "area": "гостиная", "floor": "1"},
            ]
        },
        "get_sensors_battery": {
            "items": [
                {"name": "zb_sensor_fl1_bedroom_battery", "value": 91, "area": "спальня", "floor": "1"},
            ]
        },
        "get_kettle": {},
    }
    snap = HouseSnapshot.from_ops("house", ops)
    bats = [s for s in snap.sensors if s.kind == "battery"]
    hums = [s for s in snap.sensors if s.kind == "humidity"]
    assert len(bats) == 1
    assert bats[0].area == "спальня"
    assert bats[0].unique_id == "house:sensor_battery:zb_sensor_fl1_bedroom_battery"
    assert len(hums) == 1
    from cottage_monitoring.snapshot import sensor_display_name, sensor_ha_profile
    assert sensor_display_name(name="zb_sensor_fl1_bedroom_battery", kind="battery") == "Батарея"
    assert sensor_ha_profile("meter")["state_class"] == "total_increasing"
    assert sensor_ha_profile("hour")["state_class"] == "total"
    assert sensor_ha_profile("daily")["state_class"] == "total"
    assert sensor_ha_profile("battery") == {
        "device_class": "battery",
        "unit": "%",
        "state_class": "measurement",
    }
```

Проверить slug unique_id батареи: `slug("zb_sensor_fl1_bedroom_battery")` = то же имя (уже lowercase, без пробелов).

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ha && python -m pytest tests/test_snapshot.py::test_energy_snapshot_keeps_six_keys_drops_phases tests/test_snapshot.py::test_battery_sensors_and_display_name -v
```

Expected: FAIL.

- [ ] **Step 3: Implement snapshot**

В `from_ops`:

```python
        sensors_op = ops.get("get_sensors") or {}
        battery_op = ops.get("get_sensors_battery") or {}
        energy_op = ops.get("get_energy_status") or {}
        ...
        for item in battery_op.get("items") or []:
            sensors.append(
                SensorItem(
                    name=item["name"],
                    kind="battery",
                    value=item.get("value"),
                    area=item.get("area"),
                    floor=item.get("floor"),
                    unique_id=_unique_id(house_id, "sensor_battery", item["name"]),
                )
            )
        for item in energy_op.get("items") or []:
            ga = item.get("ga")
            key = ENERGY_HA_BY_GA.get(ga)
            if not key:
                continue
            sensors.append(
                SensorItem(
                    name=ENERGY_DISPLAY_NAME[key],
                    kind=key,
                    value=item.get("value"),
                    area=None,
                    floor=None,
                    unique_id=_unique_id(house_id, "energy", key),
                )
            )
```

`sensor_display_name`: в начале

```python
    if kind == "battery":
        return "Батарея"
    if kind in ENERGY_DISPLAY_NAME:
        return ENERGY_DISPLAY_NAME[kind]
```

Комментарий `SensorItem.kind` обновить: air | floor | humidity | outdoor | battery | power | frequency | meter | hour | daily | pf.

- [ ] **Step 4: Run tests**

```bash
cd ha && python -m pytest tests -v
```

Expected: все прежние + новые PASS.

- [ ] **Step 5: Commit**

```bash
git add ha/custom_components/cottage_monitoring/snapshot.py ha/tests/test_snapshot.py
git commit -m "$(cat <<'EOF'
feat: map six energy GAs and Zigbee batteries in HA snapshot

Filter get_energy_status in HA so Telegram still sees phases. Keep humidity and battery on separate ops keys.
EOF
)"
```

---

### Task 3: Coordinator poll + sensor device classes

**Files:**
- Modify: `ha/custom_components/cottage_monitoring/coordinator.py`
- Modify: `ha/custom_components/cottage_monitoring/sensor.py`
- Test: `ha/tests/test_snapshot.py` (profile уже в Task 2) и при необходимости `ha/tests/test_commands.py` не трогать.

**Interfaces:**
- Coordinator `_async_update_data` добавляет **после** humidity, **до** kettle (порядок не важен для snapshot):

```python
                "get_sensors": await self.client.call_op(
                    "get_sensors", {"kind": "humidity"}
                ),
                "get_sensors_battery": await self.client.call_op(
                    "get_sensors", {"kind": "battery"}
                ),
                "get_energy_status": await self.client.call_op("get_energy_status"),
                "get_kettle": await self.client.call_op("get_kettle"),
```

Ключ словаря `get_sensors_battery` ≠ имя Ops. Имя Ops оба раза `get_sensors`.

- `CottageSensor._apply_device_class`: для kind из `sensor_ha_profile` (power/frequency/meter/hour/daily/pf/battery) маппить строки на HA enums. Outdoor — как сейчас по label. Humidity/air/floor могут идти через profile **или** оставить текущие ветки; не ломать outdoor.
- Маппинг единиц: `"W"` → `UnitOfPower.WATT`, `"Hz"` → `UnitOfFrequency.HERTZ`, `"kWh"` → `UnitOfEnergy.KILO_WATT_HOUR`, `"%"` → `PERCENTAGE`, `None` → без unit.
- `state_class`: `"measurement"` → `MEASUREMENT`, `"total_increasing"` → `TOTAL_INCREASING`, `"total"` → `TOTAL`.
- `device_class`: `SensorDeviceClass` с тем же value (`POWER`, `FREQUENCY`, `ENERGY`, `POWER_FACTOR`, `BATTERY`, …).
- Energy area: `area_name_for(None, None, floors)` пусто → `place_device_name` → `HOUSE_AREA_NAME` («Дом»). Уже так для unplaced. Проверить, что `CottageSensor` вызывает `place_device_name` как сейчас — батарея с area спальня остаётся в спальне.

- [ ] **Step 1: Write a failing test that coordinator source contains the two new calls**

Не импортировать `homeassistant`. AST-тест в `ha/tests/test_commands.py` или новый `ha/tests/test_coordinator_ops.py`:

```python
# ha/tests/test_coordinator_ops.py
import ast
from pathlib import Path

COORD = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "cottage_monitoring"
    / "coordinator.py"
)


def test_coordinator_polls_energy_and_battery() -> None:
    src = COORD.read_text(encoding="utf-8")
    assert 'call_op("get_energy_status")' in src or "call_op('get_energy_status')" in src
    assert '{"kind": "battery"}' in src or "{'kind': 'battery'}" in src
    assert '{"kind": "humidity"}' in src or "{'kind': 'humidity'}" in src
    tree = ast.parse(src)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "call_op"
    ]
    op_names = []
    for call in calls:
        if call.args and isinstance(call.args[0], ast.Constant):
            op_names.append(call.args[0].value)
    assert op_names.count("get_sensors") == 2
    assert "get_energy_status" in op_names
```

И тест sensor.py source (без import HA):

```python
def test_sensor_platform_uses_ha_profile_kinds() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "cottage_monitoring"
        / "sensor.py"
    ).read_text(encoding="utf-8")
    assert "sensor_ha_profile" in src
    assert "UnitOfEnergy" in src
    assert "UnitOfPower" in src
    assert "UnitOfFrequency" in src
    assert "TOTAL_INCREASING" in src
```

- [ ] **Step 2: Run to verify fail**

```bash
cd ha && python -m pytest tests/test_coordinator_ops.py -v
```

- [ ] **Step 3: Implement coordinator + sensor.py**

`sensor.py` — логика `_apply_device_class`:

```python
        from homeassistant.const import (
            PERCENTAGE,
            UnitOfEnergy,
            UnitOfFrequency,
            UnitOfPower,
            UnitOfPressure,
            UnitOfSpeed,
            UnitOfTemperature,
        )
        ...
        if kind == "outdoor":
            # existing outdoor branches unchanged
            ...
        profile = sensor_ha_profile(kind)
        dc = profile["device_class"]
        self._attr_device_class = SensorDeviceClass(dc) if dc else None
        unit = profile["unit"]
        unit_map = {
            "W": UnitOfPower.WATT,
            "Hz": UnitOfFrequency.HERTZ,
            "kWh": UnitOfEnergy.KILO_WATT_HOUR,
            "%": PERCENTAGE,
            "°C": UnitOfTemperature.CELSIUS,
        }
        self._attr_native_unit_of_measurement = unit_map.get(unit) if unit else None
        sc = profile["state_class"]
        sc_map = {
            "measurement": SensorStateClass.MEASUREMENT,
            "total": SensorStateClass.TOTAL,
            "total_increasing": SensorStateClass.TOTAL_INCREASING,
        }
        self._attr_state_class = sc_map.get(sc)
```

Outdoor ветки оставить **выше** `sensor_ha_profile`, иначе outdoor уйдёт в temperature.

- [ ] **Step 4: Run tests**

```bash
cd ha && python -m pytest tests -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ha/custom_components/cottage_monitoring/coordinator.py \
  ha/custom_components/cottage_monitoring/sensor.py \
  ha/tests/test_coordinator_ops.py
git commit -m "$(cat <<'EOF'
feat: poll energy and batteries in HA coordinator

Two extra read Ops per 30s cycle. Device classes match Energy HA (meter total_increasing, hour/daily total).
EOF
)"
```

---

### Task 4: Lovelace «Графики», Grafana embed, Energy template, pin 0.3.4, docs

**Files:**
- Create: `server/deploy/ha/dashboards/graphs.yaml`
- Modify: `server/deploy/ha/configuration.yaml`
- Create: `server/deploy/ha/energy-grid.example.json`
- Create: `server/deploy/grafana/grafana-embedding.ini.snippet`
- Modify: `server/deploy/grafana/README.md` (строка про embedding)
- Modify: `server/pyproject.toml` (`version = "0.3.4"`)
- Modify: `server/deploy/IMAGE_PIN.yaml`
- Modify: `server/deploy/cottage-monitoring.service` (тег `0.3.4`)
- Modify: `specs/001-server-mqtt-ingestor/quickstart.md`
- Modify: `specs/001-server-mqtt-ingestor/research.md` (R-027)
- Modify: `docs/superpowers/specs/2026-08-28-ha-nord-design.md` — строка «не регистрируем get_energy_status / батареи» → ссылка на energy-спеку как выполненную волну (ещё не live — «код готов, live Task 5»).

**Не** менять `ENERGY_SUMMARY_GAS`. **Не** открывать Grafana anonymously.

- [ ] **Step 1: Lovelace YAML**

`server/deploy/ha/dashboards/graphs.yaml`:

```yaml
title: Графики
views:
  - title: Графики
    path: graphs
    cards:
      - type: markdown
        content: |
          Графики строит Grafana (SELECT). Если рамка пустая — откройте ссылку (нужен логин Grafana).
          - [Electricity](https://elion.black-castle.ru/grafana/d/cottage-energy/)
          - [Batteries](https://elion.black-castle.ru/grafana/d/cottage-batteries/)
      - type: iframe
        url: https://elion.black-castle.ru/grafana/d/cottage-energy/?orgId=1&kiosk
        aspect_ratio: 75%
      - type: iframe
        url: https://elion.black-castle.ru/grafana/d/cottage-batteries/?orgId=1&kiosk
        aspect_ratio: 55%
```

`configuration.yaml` — **добавить**, не удаляя `cottage_monitoring:`:

```yaml
lovelace:
  dashboards:
    cottage-graphs:
      mode: yaml
      title: Графики
      icon: mdi:chart-areaspline
      show_in_sidebar: true
      filename: dashboards/graphs.yaml
```

Не ставить `lovelace.mode: yaml` на весь UI — Overview (storage/strategy) должен остаться.

- [ ] **Step 2: Energy example JSON**

`server/deploy/ha/energy-grid.example.json` — комментарий в соседнем markdown не заводить. В JSON нельзя комментарии; положить рядом короткий блок в research. Содержимое example:

```json
{
  "version": 1,
  "minor_version": 1,
  "key": "energy",
  "data": {
    "energy_sources": [
      {
        "type": "grid",
        "flow_from": [
          {
            "stat_energy_from": "REPLACE_WITH_ENTITY_ID_OF_unique_id_house:energy:meter",
            "stat_cost": null,
            "entity_energy_price": null,
            "number_energy_price": null
          }
        ],
        "flow_to": []
      }
    ],
    "device_consumption": []
  }
}
```

Live Task 5 подставит реальный `entity_id` (обычно транслит «Счётчик»). Живая мощность «Сейчас»: если в UI Energy есть поле Power — указать entity unique_id `house:energy:power`. Если поля нет — шесть карточек в «Дом» достаточны; не выдумывать ключ JSON.

- [ ] **Step 3: Grafana snippet**

`server/deploy/grafana/grafana-embedding.ini.snippet`:

```ini
# Merge into /etc/grafana/grafana.ini [security] on elion. Do not enable anonymous auth.
[security]
allow_embedding = true
```

README: одна фраза — iframe с `ha.black-castle.ru` требует `allow_embedding`; cookie cross-subdomain может не пройти → ссылка в Lovelace.

- [ ] **Step 4: Pin 0.3.4 + R-027 + quickstart**

`IMAGE_PIN.yaml`:

```yaml
version: "0.3.4"
git_ref: "main"
image_tag: "cottage-monitoring:0.3.4"
image_digest: ""
overlay_retired: true
replaces_overlay: "cottage-monitoring:0.3.3"
notes: |
  v0.3.4: get_sensors kind=battery (ROOM_BATTERY). HA energy tiles use existing get_energy_status unchanged.
```

R-027 в research (после R-026): HA poll +2 read; 6 GA allowlist в snapshot; ЖКХ `32/1/59`; hour/daily `state_class=total`; Grafana iframe UID `cottage-energy` / `cottage-batteries`; fallback ссылка; каталог 17.

Quickstart: текущий pin **0.3.4**; poll Ops перечислить 8 вызовов (6 старых + energy + battery); entity unique_id `house:energy:meter`; вкладка Графики.

- [ ] **Step 5: Commit**

```bash
git add server/deploy/ha/dashboards/graphs.yaml \
  server/deploy/ha/configuration.yaml \
  server/deploy/ha/energy-grid.example.json \
  server/deploy/grafana/grafana-embedding.ini.snippet \
  server/deploy/grafana/README.md \
  server/pyproject.toml \
  server/deploy/IMAGE_PIN.yaml \
  server/deploy/cottage-monitoring.service \
  specs/001-server-mqtt-ingestor/quickstart.md \
  specs/001-server-mqtt-ingestor/research.md \
  docs/superpowers/specs/2026-08-28-ha-nord-design.md
git commit -m "$(cat <<'EOF'
docs: pin Nord 0.3.4 and ship HA energy Grafana dashboard files

HA Lovelace graphs view embeds Grafana SELECT dashboards with a login fallback. Specs record the six-GA allowlist.
EOF
)"
```

---

### Task 5: Live elion — Nord 0.3.4, HA sync, Grafana embed, Energy, проверка

**Порядок обязателен:** Nord → dry-run battery/energy → sync HA → Grafana embed → Lovelace/config → Energy UI → browser.

- [ ] **Step 1: Собрать и выкатить Nord 0.3.4**

Из `server/` (код не копировать на elion):

```bash
docker build --platform linux/amd64 -t cottage-monitoring:0.3.4 -f deploy/Dockerfile .
docker save cottage-monitoring:0.3.4 | ssh elion 'sudo docker load'
# unit pin: содержимое server/deploy/cottage-monitoring.service → /etc/systemd/system/cottage-monitoring.service
# (scp unit или tee; не git clone продукта)
ssh elion 'sudo systemctl daemon-reload && sudo systemctl restart cottage-monitoring'
ssh elion '/opt/cottage-monitoring/wait_http_health.sh http://127.0.0.1:8321/health 30'
```

Alembic не гонять.

Dry-run (ключ HA на elion, не печатать секрет в отчёт):

```bash
# get_sensors battery и get_energy_status через REST POST /api/v1/houses/house/ops/...
# battery items: names *_battery, area/floor где есть
# energy items: полный набор включая фазы; в HA потом только 6
```

- [ ] **Step 2: Sync HA component + dashboards YAML**

```bash
./server/deploy/ha-sync-component.sh
# скопировать graphs.yaml и configuration.yaml на volume:
# /var/lib/homeassistant/dashboards/graphs.yaml
# влить lovelace: dashboards cottage-graphs в configuration.yaml на volume (не затереть secrets)
ssh elion 'sudo systemctl restart home-assistant'
```

`http:` в YAML не возвращать.

- [ ] **Step 3: Grafana allow_embedding**

На elion: в `/etc/grafana/grafana.ini` секция `[security]` → `allow_embedding = true`. **Не** включать `[auth.anonymous] enabled = true`. `systemctl restart grafana-server` (или grafana). Проверка: `curl -sI https://elion.black-castle.ru/grafana/login | head`.

- [ ] **Step 4: Energy HA**

После первого успешного poll найти entity_id по unique_id `house:energy:meter` в `.storage/core.entity_registry`. Settings → Energy: grid consumption = **Счётчик**; power если есть поле = **Сейчас**. Зафиксировать фактический entity_id в quickstart (одна строка). Не заводить тариф.

- [ ] **Step 5: Verify + spec Implemented**

Проверки:
1. Area «Дом»: Сейчас, Частота, Счётчик, За час, За сутки, PF. Без GA в имени.
2. Комната со Zigbee (спальня): Батарея %.
3. Telegram/`get_energy_status` dry-run: items с фазами на месте.
4. Вкладка Графики: iframe **или** рабочие ссылки (если iframe логин — это успех по спеке, не баг).
5. `GET /api/v1/ops` — 17 имён.

Обновить спеку energy: **Status: Implemented**. R-027 live-абзац: entity_id, iframe vs ссылка.

```bash
git add docs/superpowers/specs/2026-08-28-ha-energy-grafana-design.md \
  specs/001-server-mqtt-ingestor/quickstart.md \
  specs/001-server-mqtt-ingestor/research.md
git commit -m "$(cat <<'EOF'
docs: mark HA energy Grafana wave implemented after elion verify

Record live entity_ids and whether Grafana iframe or link fallback won.
EOF
)"
```

Если live заблокирован (нет docker/SSH) — **BLOCKED** с тем, что уже в git; не помечать спеку Implemented.

---

## Spec coverage (self-review)

| Спека | Задача |
|-------|--------|
| 6 чисел, allowlist, не 32/1/39 | Task 2 |
| hour/daily `total`, meter `total_increasing` | Task 2–3 |
| Energy HA grid = Счётчик | Task 4–5 |
| Батарея, kind=battery, placement | Task 1–3 |
| Poll +2, каталог 17, Op не режем | Task 1, 3, 5 |
| Lovelace Графики, iframe/ссылка, не anonymous | Task 4–5 |
| Ошибки: нет GA → остальные живы; 5xx → UpdateFailed | Task 2, 3 (coordinator без частичного retry — как остальные Ops) |
| Тесты snapshot/Nord/drift | Task 1–3 |
| Live elion | Task 5 |

Non-goals соблюдены: фазы не в HA; MQTT нет; People/чайник/config flow не трогаем.
