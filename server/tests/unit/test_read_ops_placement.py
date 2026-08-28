# server/tests/unit/test_read_ops_placement.py
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from cottage_monitoring.services import agent_actions
from cottage_monitoring.services.object_resolver import ObjectRole, ResolvedObject, ResolveResult


def _ro(ga: str, name: str, tags: list[str], role: ObjectRole) -> ResolvedObject:
    return ResolvedObject(ga=ga, name=name, tags=tags, role=role, datatype=1)


def test_list_lights_items_include_area_and_floor(monkeypatch) -> None:
    kitchen = _ro("1/1/7", "Свет - кухня", ["1floor", "control", "light"], ObjectRole.LIGHT_CONTROL)

    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ok", matches=[kitchen])

    async def fake_states(*_a, **_k):
        return {"1/1/7": True}

    async def fake_status(*_a, **_k):
        return {}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)
    monkeypatch.setattr(agent_actions, "_light_status_by_control_name", fake_status)

    out = asyncio.run(agent_actions.list_lights(MagicMock(), "house"))
    item = out["items"][0]
    assert item["area"] == "кухня"
    assert item["floor"] == "1"
    assert item["name"] == "Свет - кухня"
    assert "ga" in item


def test_get_climate_zone_has_area_floor_and_keeps_room(monkeypatch) -> None:
    sp = _ro(
        "1/6/5",
        "Уставка ТП - гостиная 1",
        ["1floor", "heat", "setpoint", "temp"],
        ObjectRole.CLIMATE_SETPOINT,
    )

    async def fake_resolve(_session, _house_id, *, query=None, role=None, **_k):
        if role == ObjectRole.CLIMATE_SETPOINT:
            return ResolveResult(status="ok", matches=[sp])
        return ResolveResult(status="not_found", matches=[])

    async def fake_states(*_a, **_k):
        return {"1/6/5": 23, "1/7/1": True}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)

    out = asyncio.run(agent_actions.get_climate(MagicMock(), "house"))
    zone = out["zones"][0]
    assert zone["room"] == "гостиная 1"
    assert zone["area"] == "гостиная"
    assert zone["floor"] == "1"


def test_get_temperature_zigbee_maps_english_name(monkeypatch) -> None:
    sensor = _ro(
        "33/1/13",
        "zb_sensor_fl1_kitchen_temperature",
        ["floor1", "temperature", "zb_sensor"],
        ObjectRole.ROOM_TEMP,
    )

    async def fake_resolve(_session, _house_id, *, role=None, query=None, kind=None, **_k):
        if role == ObjectRole.ROOM_TEMP:
            return ResolveResult(status="ok", matches=[sensor])
        return ResolveResult(status="ok", matches=[])

    async def fake_states(*_a, **_k):
        return {"33/1/13": 21.5}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)

    out = asyncio.run(agent_actions.get_temperatures(MagicMock(), "house", query="кухня"))
    item = next(i for i in out["items"] if i["ga"] == "33/1/13")
    assert item["area"] == "кухня"
    assert item["floor"] == "1"
    assert item["source"] == "air"


def test_get_sensors_humidity_has_placement(monkeypatch) -> None:
    hum = _ro(
        "33/1/14",
        "zb_sensor_fl1_kitchen_humidity",
        ["floor1", "humidity", "zb_sensor"],
        ObjectRole.ROOM_HUMIDITY,
    )

    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ok", matches=[hum])

    async def fake_states(*_a, **_k):
        return {"33/1/14": 45}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)

    out = asyncio.run(agent_actions.get_sensors(MagicMock(), "house", kind="humidity"))
    assert out["items"][0]["area"] == "кухня"
    assert out["items"][0]["floor"] == "1"


def test_get_sensors_unknown_kind_still_raises(monkeypatch) -> None:
    async def fake_states(*_a, **_k):
        return {}

    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)

    with pytest.raises(ValueError):
        asyncio.run(agent_actions.get_sensors(MagicMock(), "house", kind="not-a-kind"))


def test_get_kettle_forwards_placement_when_classifiable(monkeypatch) -> None:
    from types import SimpleNamespace

    matches = [
        SimpleNamespace(
            ga="33/1/37",
            name="ble_teapot_RK-M173S_temp",
            tags=["ble", "teapot", "temp"],
            role=ObjectRole.ZIGBEE_APPLIANCE,
        ),
    ]

    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ok", matches=matches)  # type: ignore[arg-type]

    async def fake_states(*_a, **_k):
        return {"33/1/37": 54}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)

    out = asyncio.run(agent_actions.get_kettle(MagicMock(), "house"))
    appliance = out["appliance"]
    assert "area" not in appliance
