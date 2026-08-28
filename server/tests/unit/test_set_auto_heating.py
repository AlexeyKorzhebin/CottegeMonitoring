from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.params import SetAutoHeatingParams, validate_params
from cottage_monitoring.ops.registry import registry
from cottage_monitoring.services import agent_actions
from cottage_monitoring.services.object_resolver import AUTO_HEATING_GA


def test_set_auto_heating_params_require_on() -> None:
    load_catalog()
    spec = registry.get("set_auto_heating")
    with pytest.raises(HTTPException) as ei:
        validate_params(spec, {})
    assert ei.value.status_code == 422
    parsed = SetAutoHeatingParams(on=False)
    assert parsed.on is False


def test_set_auto_heating_writes_1_7_1(monkeypatch) -> None:
    sent: list[tuple] = []

    async def fake_send(session, house_id, ga, value, *, comment=None):
        sent.append((house_id, ga, value, comment))
        return {"request_id": "r1", "ga": ga, "value": value, "status": "sent"}

    monkeypatch.setattr(agent_actions, "_resolve_device_and_send", fake_send)
    out = asyncio.run(agent_actions.set_auto_heating(None, "house", on=False))
    assert sent[0][1] == AUTO_HEATING_GA
    assert sent[0][1] == "1/7/1"
    assert sent[0][2] is False
    assert "set_auto_heating" in (sent[0][3] or "")
    assert out["status"] == "sent"
