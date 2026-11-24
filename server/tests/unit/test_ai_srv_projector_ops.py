"""Tests for get/set_ai_srv_switcher and get/set_projector ops."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from cottage_monitoring.services import agent_actions


def test_get_ai_srv_switcher_reads_status_and_metrics(monkeypatch) -> None:
    async def fake_states(_session, _house_id: str) -> dict:
        return {
            "32/6/5": False,
            "32/6/6": True,
            "35/1/20": 82.0,
            "35/1/21": 0.54,
            "35/1/22": 202.88,
            "35/1/23": 27.86,
        }

    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)
    out = asyncio.run(agent_actions.get_ai_srv_switcher(None, "house"))  # type: ignore[arg-type]
    assert out["on"] is True
    assert out["power_w"] == 82.0
    assert out["current_a"] == 0.54
    assert out["voltage_v"] == 202.88
    assert out["energy_kwh"] == 27.86
    assert out["cmd_ga"] == "32/6/5"
    assert out["status_ga"] == "32/6/6"


def test_get_ai_srv_switcher_falls_back_to_cmd(monkeypatch) -> None:
    async def fake_states(_session, _house_id: str) -> dict:
        return {"32/6/5": True}

    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)
    out = asyncio.run(agent_actions.get_ai_srv_switcher(None, "house"))  # type: ignore[arg-type]
    assert out["on"] is True
    assert out["power_w"] is None


def test_get_projector_reads_status(monkeypatch) -> None:
    async def fake_states(_session, _house_id: str) -> dict:
        return {"32/6/2": True, "32/6/3": False}

    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)
    out = asyncio.run(agent_actions.get_projector(None, "house"))  # type: ignore[arg-type]
    assert out["on"] is False
    assert out["cmd_ga"] == "32/6/2"
    assert out["status_ga"] == "32/6/3"


def test_set_ai_srv_switcher_writes_cmd(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_send(session, house_id, ga, value, *, comment=None):
        sent.append({"ga": ga, "value": value, "comment": comment})
        return {"request_id": "r1", "ga": ga, "value": value, "status": "sent"}

    monkeypatch.setattr(agent_actions, "_resolve_device_and_send", fake_send)
    out = asyncio.run(
        agent_actions.set_ai_srv_switcher(None, "house", on=False)  # type: ignore[arg-type]
    )
    assert sent == [
        {"ga": "32/6/5", "value": False, "comment": "mcp set_ai_srv_switcher"}
    ]
    assert out["status"] == "sent"


def test_set_projector_writes_cmd(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_send(session, house_id, ga, value, *, comment=None):
        sent.append({"ga": ga, "value": value})
        return {"request_id": "r2", "ga": ga, "value": value, "status": "sent"}

    monkeypatch.setattr(agent_actions, "_resolve_device_and_send", fake_send)
    out = asyncio.run(agent_actions.set_projector(None, "house", on=True))  # type: ignore[arg-type]
    assert sent == [{"ga": "32/6/2", "value": True}]
    assert out["ga"] == "32/6/2"


def test_catalog_registers_ai_srv_and_projector_ops() -> None:
    from cottage_monitoring.ops import catalog, registry

    catalog.load_catalog()
    names = {spec.name for spec in registry.all_ops()}
    assert "get_ai_srv_switcher" in names
    assert "set_ai_srv_switcher" in names
    assert "get_projector" in names
    assert "set_projector" in names
