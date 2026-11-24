"""Ceiling Zigbee light facade: catalog map, list enrichment, set control GAs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from cottage_monitoring.models.object import Object
from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.params import validate_params
from cottage_monitoring.ops.registry import registry
from cottage_monitoring.services.object_resolver import ObjectRole

_REPO = Path(__file__).resolve().parents[3]
_CM_CLIENT_CATALOG = _REPO / "cm-client/scripts/zb_ceiling_light_catalog.json"


def _obj(ga: str, name: str, tags: str, datatype: int = 1001) -> Object:
    return Object(
        house_id="h1",
        ga=ga,
        name=name,
        datatype=datatype,
        tags=tags,
        is_active=True,
        is_timeseries=False,
    )


def test_catalog_matches_cm_client_sot() -> None:
    from cottage_monitoring.services.ceiling_light_params import catalog_path, load_catalog_rows

    rows = load_catalog_rows()
    raw = json.loads(_CM_CLIENT_CATALOG.read_text(encoding="utf-8"))
    assert rows == raw
    assert catalog_path().is_file()


def test_params_for_relay_uses_exact_catalog_gas() -> None:
    from cottage_monitoring.services.ceiling_light_params import params_for_relay

    tima = params_for_relay("1/1/13")
    assert tima is not None
    assert tima.zone == "Тима"
    assert tima.brightness.control == "36/1/1"
    assert tima.brightness.status == "36/2/1"
    assert tima.color_temp.control == "36/1/2"
    assert tima.color_temp.status == "36/2/2"
    assert tima.rgb.control == "36/1/3"
    assert tima.rgb.status == "36/2/3"

    hall = params_for_relay("1/1/15")
    assert hall is not None
    assert hall.brightness.control == "36/1/4"
    assert hall.color_temp.control == "36/1/5"
    assert hall.rgb.control == "36/1/6"

    office = params_for_relay("1/1/14")
    assert office is not None
    assert office.brightness.control == "36/1/7"
    assert office.color_temp.control == "36/1/8"
    assert office.rgb.control == "36/1/9"

    assert params_for_relay("1/1/7") is None


def test_packaged_catalog_matches_cm_client_when_both_exist() -> None:
    packaged = (
        Path(__file__).resolve().parents[2]
        / "src/cottage_monitoring/data/zb_ceiling_light_catalog.json"
    )
    assert packaged.is_file(), "Docker image copies src/; keep a snapshot of the cm-client catalog"
    assert packaged.read_bytes() == _CM_CLIENT_CATALOG.read_bytes()


def test_set_light_params_require_on_or_param() -> None:
    load_catalog()
    spec = registry.get("set_light")
    with pytest.raises(HTTPException) as ei:
        validate_params(spec, {"query": "тима"})
    assert ei.value.status_code == 422

    parsed = validate_params(spec, {"query": "тима", "brightness": 50})
    assert parsed["on"] is None
    assert parsed["brightness"] == 50
    assert validate_params(spec, {"query": "тима", "on": False})["on"] is False

    with pytest.raises(HTTPException):
        validate_params(spec, {"query": "тима", "brightness": 101})
    with pytest.raises(HTTPException):
        validate_params(spec, {"query": "тима", "rgb": -1})


def test_set_lights_params_require_on_or_param() -> None:
    load_catalog()
    spec = registry.get("set_lights")
    with pytest.raises(HTTPException) as ei:
        validate_params(spec, {"query": "2 этаж"})
    assert ei.value.status_code == 422
    parsed = validate_params(spec, {"query": "2 этаж", "color_temp": 250})
    assert parsed["on"] is None
    assert parsed["color_temp"] == 250
    assert parsed["skip_unchanged"] is True


def test_list_lights_enriches_status_gas_for_catalog_relay(monkeypatch) -> None:
    from cottage_monitoring.services import agent_actions, object_resolver

    tima = _obj("1/1/13", "Свет - спальня Тима", "2floor,control,light")
    tima_st = _obj("1/2/13", "Свет - спальня Тима :status", "light,status")
    kitchen = _obj("1/1/7", "Свет - кухня", "1floor,control,light")
    kitchen_st = _obj("1/2/7", "Свет - кухня :status", "light,status")

    async def fake_load(_session, _house_id: str) -> list[Object]:
        return [tima, tima_st, kitchen, kitchen_st]

    async def fake_states(_session, _house_id: str) -> dict:
        return {
            "1/1/13": False,
            "1/2/13": True,
            "1/1/7": True,
            "1/2/7": True,
            "36/2/1": 40,
            "36/2/2": 300,
            "36/2/3": 16711680,
        }

    monkeypatch.setattr(object_resolver, "load_active_objects", fake_load)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)

    out = asyncio.run(agent_actions.list_lights(None, "h1"))  # type: ignore[arg-type]
    by_ga = {item["ga"]: item for item in out["items"]}

    assert by_ga["1/1/13"]["on"] is True
    assert by_ga["1/1/13"]["brightness"] == 40
    assert by_ga["1/1/13"]["color_temp"] == 300
    assert by_ga["1/1/13"]["rgb"] == 16711680

    assert by_ga["1/1/7"]["on"] is True
    assert "brightness" not in by_ga["1/1/7"]
    assert "color_temp" not in by_ga["1/1/7"]
    assert "rgb" not in by_ga["1/1/7"]


def test_set_lights_writes_catalog_control_gas_and_turns_relay_on(monkeypatch) -> None:
    from cottage_monitoring.services import agent_actions, object_resolver

    tima = _obj("1/1/13", "Свет - спальня Тима", "2floor,control,light")

    async def fake_load(_session, _house_id: str) -> list[Object]:
        return [tima]

    async def fake_states(_session, _house_id: str) -> dict:
        return {"1/1/13": False, "1/2/13": False}

    sent: list[dict] = []

    async def fake_batch(session, house_id, *, targets=None, value=None, items=None, comment):
        sent.append({"targets": targets, "value": value, "items": items})
        n = len(items) if items is not None else len(targets or [])
        return {"request_id": "r1", "status": "sent", "item_count": n, "send_ms": 1}

    monkeypatch.setattr(object_resolver, "load_active_objects", fake_load)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)
    monkeypatch.setattr(agent_actions, "_send_light_batch", fake_batch)

    result = asyncio.run(
        agent_actions.set_lights(
            None,  # type: ignore[arg-type]
            "h1",
            query="Свет - спальня Тима",
            brightness=50,
            color_temp=250,
            rgb=0x112233,
        )
    )
    assert result["status"] == "sent"
    payload = sent[0]["items"] if sent[0]["items"] is not None else [
        {"ga": ga, "value": sent[0]["value"]} for ga, _name in sent[0]["targets"]
    ]
    assert payload == [
        {"ga": "1/1/13", "value": True},
        {"ga": "36/1/1", "value": 50},
        {"ga": "36/1/2", "value": 250},
        {"ga": "36/1/3", "value": 0x112233},
    ]


def test_set_lights_on_false_does_not_write_param_gas(monkeypatch) -> None:
    from cottage_monitoring.services import agent_actions, object_resolver

    tima = _obj("1/1/13", "Свет - спальня Тима", "2floor,control,light")

    async def fake_load(_session, _house_id: str) -> list[Object]:
        return [tima]

    async def fake_states(_session, _house_id: str) -> dict:
        return {"1/1/13": True, "1/2/13": True}

    sent: list[dict] = []

    async def fake_batch(session, house_id, *, targets=None, value=None, items=None, comment):
        sent.append({"targets": targets, "value": value, "items": items})
        n = len(items) if items is not None else len(targets or [])
        return {"request_id": "r1", "status": "sent", "item_count": n, "send_ms": 1}

    monkeypatch.setattr(object_resolver, "load_active_objects", fake_load)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)
    monkeypatch.setattr(agent_actions, "_send_light_batch", fake_batch)

    asyncio.run(
        agent_actions.set_lights(
            None,  # type: ignore[arg-type]
            "h1",
            query="Свет - спальня Тима",
            on=False,
            brightness=80,
        )
    )
    payload = sent[0]["items"] if sent[0]["items"] is not None else [
        {"ga": ga, "value": sent[0]["value"]} for ga, _name in sent[0]["targets"]
    ]
    assert payload == [{"ga": "1/1/13", "value": False}]


def test_set_light_writes_catalog_control_gas(monkeypatch) -> None:
    from cottage_monitoring.services import agent_actions, object_resolver

    hall = _obj("1/1/15", "Свет - холл 2 этаж", "2floor,control,light")

    async def fake_load(_session, _house_id: str) -> list[Object]:
        return [hall]

    sent: list[dict] = []

    async def fake_batch(session, house_id, *, targets=None, value=None, items=None, comment):
        sent.append({"targets": targets, "value": value, "items": items})
        n = len(items) if items is not None else len(targets or [])
        return {"request_id": "r1", "status": "sent", "item_count": n, "send_ms": 1}

    monkeypatch.setattr(object_resolver, "load_active_objects", fake_load)
    monkeypatch.setattr(agent_actions, "_send_light_batch", fake_batch)

    result = asyncio.run(
        agent_actions.set_light(
            None,  # type: ignore[arg-type]
            "h1",
            query="Свет - холл 2 этаж",
            brightness=10,
        )
    )
    assert result["status"] == "sent"
    payload = sent[0]["items"] if sent[0]["items"] is not None else [
        {"ga": ga, "value": sent[0]["value"]} for ga, _name in sent[0]["targets"]
    ]
    assert payload == [
        {"ga": "1/1/15", "value": True},
        {"ga": "36/1/4", "value": 10},
    ]


def test_send_light_batch_accepts_non_bool_values(monkeypatch) -> None:
    from cottage_monitoring.services import agent_actions

    relay = _obj("1/1/13", "Свет - спальня Тима", "2floor,control,light")
    relay.device_id = "lm-1"
    bri = _obj("36/1/1", "Свет Zigbee - Тима - яркость", "2floor,light,zigbee,zigbee_send", 5)
    bri.device_id = "lm-1"

    class _Result:
        def __init__(self, obj):
            self._obj = obj

        def scalar_one_or_none(self):
            return self._obj

    class _Session:
        def __init__(self):
            self.committed = False
            self._queue = [relay, bri]

        async def execute(self, _query):
            return _Result(self._queue.pop(0))

        async def commit(self):
            self.committed = True

    sent: list[dict] = []

    async def fake_send(house_id, device_id, payload, *, session=None):
        sent.append(payload)

        class _Cmd:
            request_id = "rid"
            status = "sent"

        return _Cmd()

    monkeypatch.setattr(agent_actions, "send_command", fake_send)

    session = _Session()
    out = asyncio.run(
        agent_actions._send_light_batch(
            session,  # type: ignore[arg-type]
            "h1",
            items=[{"ga": "1/1/13", "value": True}, {"ga": "36/1/1", "value": 50}],
            comment="test",
        )
    )
    assert out["item_count"] == 2
    assert sent[0]["items"] == [
        {"ga": "1/1/13", "value": True},
        {"ga": "36/1/1", "value": 50},
    ]


def test_resolve_light_kind_skips_param_objects(monkeypatch) -> None:
    import asyncio as aio

    from cottage_monitoring.services import object_resolver
    from cottage_monitoring.services.object_resolver import resolve_objects

    relay = _obj("1/1/13", "Свет - спальня Тима", "2floor,control,light")
    param = _obj("36/1/1", "Свет Zigbee - Тима - яркость", "2floor,light,zigbee,zigbee_send")
    status = _obj("36/2/1", "Свет Zigbee - Тима - яркость:status", "2floor,light,zigbee,status")

    async def fake_load(_session, _house_id: str) -> list[Object]:
        return [relay, param, status]

    monkeypatch.setattr(object_resolver, "load_active_objects", fake_load)

    result = aio.run(
        resolve_objects(None, "h1", kind="light")  # type: ignore[arg-type]
    )
    assert {m.ga for m in result.matches} == {"1/1/13"}
    assert all(m.role == ObjectRole.LIGHT_CONTROL for m in result.matches)
