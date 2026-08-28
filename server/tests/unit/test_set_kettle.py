from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.params import validate_params
from cottage_monitoring.ops.registry import registry
from cottage_monitoring.services import agent_actions
from cottage_monitoring.services.object_resolver import ObjectRole, ResolvedObject, ResolveResult


def test_set_kettle_params_require_on_or_setpoint() -> None:
    load_catalog()
    spec = registry.get("set_kettle")
    with pytest.raises(HTTPException) as ei:
        validate_params(spec, {})
    assert ei.value.status_code == 422
    with pytest.raises(HTTPException):
        validate_params(spec, {"setpoint_c": 20})
    assert validate_params(spec, {"on": True}) == {"on": True, "setpoint_c": None}
    assert validate_params(spec, {"setpoint_c": 80})["setpoint_c"] == 80.0


def test_set_kettle_on_writes_cmd_ga(monkeypatch) -> None:
    cmd = ResolvedObject(
        ga="33/1/39",
        name="ble_teapot_RK-M173S_cmd",
        tags=["ble", "control", "zigbee_send"],
        role=ObjectRole.ZIGBEE_APPLIANCE,
        datatype=1,
    )

    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ok", matches=[cmd])

    sent: list[tuple] = []

    async def fake_send(session, house_id, ga, value, *, comment=None):
        sent.append((ga, value))
        return {"request_id": "r1", "ga": ga, "value": value, "status": "sent"}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_resolve_device_and_send", fake_send)

    asyncio.run(agent_actions.set_kettle(None, "house", on=True, setpoint_c=None))
    assert sent == [("33/1/39", True)]


def test_set_kettle_setpoint_does_not_write_cmd_bool(monkeypatch) -> None:
    sp = ResolvedObject(
        ga="33/1/40",
        name="ble_teapot_RK-M173S_setpoint",
        tags=["ble", "teapot", "setpoint"],
        role=ObjectRole.ZIGBEE_APPLIANCE,
        datatype=9,
    )

    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ok", matches=[sp])

    sent: list[tuple] = []

    async def fake_send(session, house_id, ga, value, *, comment=None):
        sent.append((ga, value))
        return {"request_id": "r1", "ga": ga, "value": value, "status": "sent"}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_resolve_device_and_send", fake_send)

    asyncio.run(agent_actions.set_kettle(None, "house", on=None, setpoint_c=80))
    assert sent == [("33/1/40", 80)]
    assert all(ga != "33/1/39" for ga, _ in sent)


def test_set_kettle_setpoint_404_when_object_missing(monkeypatch) -> None:
    cmd = ResolvedObject(
        ga="33/1/39",
        name="ble_teapot_RK-M173S_cmd",
        tags=["ble", "control", "zigbee_send"],
        role=ObjectRole.ZIGBEE_APPLIANCE,
        datatype=1,
    )

    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ok", matches=[cmd])

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)

    with pytest.raises(HTTPException) as ei:
        asyncio.run(agent_actions.set_kettle(None, "house", on=None, setpoint_c=80))
    assert ei.value.status_code == 404
    assert "setpoint" in str(ei.value.detail).lower()


def _kettle_cmd(**kwargs) -> ResolvedObject:
    defaults = dict(
        ga="33/1/39",
        name="ble_teapot_RK-M173S_cmd",
        tags=["ble", "control", "zigbee_send"],
        role=ObjectRole.ZIGBEE_APPLIANCE,
        datatype=1,
    )
    defaults.update(kwargs)
    return ResolvedObject(**defaults)


def _kettle_setpoint(**kwargs) -> ResolvedObject:
    defaults = dict(
        ga="33/1/40",
        name="ble_teapot_RK-M173S_setpoint",
        tags=["ble", "teapot", "setpoint", "control", "zigbee_send"],
        role=ObjectRole.ZIGBEE_APPLIANCE,
        datatype=9,
    )
    defaults.update(kwargs)
    return ResolvedObject(**defaults)


def _patch_kettle(monkeypatch, matches):
    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ok", matches=list(matches))

    sent: list[tuple] = []

    async def fake_send(session, house_id, ga, value, *, comment=None):
        sent.append((ga, value))
        return {"request_id": "r1", "ga": ga, "value": value, "status": "sent"}

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions, "_resolve_device_and_send", fake_send)
    return sent


def test_set_kettle_on_and_setpoint_writes_both_gas(monkeypatch) -> None:
    cmd = _kettle_cmd()
    sp = _kettle_setpoint()
    sent = _patch_kettle(monkeypatch, [cmd, sp])

    asyncio.run(agent_actions.set_kettle(None, "house", on=True, setpoint_c=80))

    assert sent == [("33/1/40", 80), ("33/1/39", True)]
    assert all(not (ga == "33/1/39" and value == 80) for ga, value in sent)


def test_set_kettle_keeps_setpoint_when_cmd_ambiguous(monkeypatch) -> None:
    cmd_a = _kettle_cmd()
    cmd_b = _kettle_cmd(ga="33/1/41", name="ble_teapot_RK-M173S_cmd_aux")
    sp = _kettle_setpoint()
    sent = _patch_kettle(monkeypatch, [cmd_a, cmd_b, sp])

    result = asyncio.run(agent_actions.set_kettle(None, "house", on=True, setpoint_c=80))

    assert result["status"] == "ambiguous"
    assert "setpoint" in result
    assert result["setpoint"]["ga"] == "33/1/40"
    assert sent == [("33/1/40", 80)]
    assert all(c["ga"] != "33/1/40" for c in result["candidates"])


def test_set_kettle_keeps_setpoint_when_cmd_404(monkeypatch) -> None:
    sp = _kettle_setpoint(tags=["ble", "teapot", "setpoint"])
    sent = _patch_kettle(monkeypatch, [sp])

    class _Empty:
        def scalar_one_or_none(self):
            return None

    class _Session:
        async def execute(self, *_a, **_k):
            return _Empty()

    with pytest.raises(HTTPException) as ei:
        asyncio.run(agent_actions.set_kettle(_Session(), "house", on=True, setpoint_c=80))
    assert ei.value.status_code == 404
    assert sent == [("33/1/40", 80)]
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert "setpoint" in detail
    assert detail["setpoint"]["ga"] == "33/1/40"
