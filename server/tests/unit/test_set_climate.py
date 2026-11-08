from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from cottage_monitoring.models.object import Object
from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.params import validate_params
from cottage_monitoring.ops.registry import registry
from cottage_monitoring.services import agent_actions
from cottage_monitoring.services.object_resolver import ObjectRole, ResolvedObject, ResolveResult


def _obj(ga: str, name: str, tags: str, *, active: bool = True) -> Object:
    return Object(
        house_id="h1",
        ga=ga,
        name=name,
        datatype=9,
        tags=tags,
        is_active=active,
        is_timeseries=False,
    )


def _session(obj: Object | None):
    class _Result:
        def scalar_one_or_none(self):
            return obj

    class _Session:
        async def execute(self, _query):
            return _Result()

    return _Session()


def test_set_climate_params_require_query_or_ga() -> None:
    load_catalog()
    spec = registry.get("set_climate")
    with pytest.raises(HTTPException) as ei:
        validate_params(spec, {"setpoint_c": 22})
    assert ei.value.status_code == 422
    assert validate_params(spec, {"query": "кухня", "setpoint_c": 22.0})["query"] == "кухня"
    parsed = validate_params(spec, {"ga": "1/6/7", "setpoint_c": 22.0})
    assert parsed["ga"] == "1/6/7"
    assert parsed["query"] is None
    both = validate_params(spec, {"query": "кухня", "ga": "1/6/7", "setpoint_c": 23.0})
    assert both["query"] == "кухня"
    assert both["ga"] == "1/6/7"


def test_set_climate_by_ga_skips_resolver(monkeypatch) -> None:
    obj = _obj("1/6/7", "Уставка ТП - кухня", "setpoint,heat")
    sent: list[tuple] = []

    async def fake_send(session, house_id, ga, value, *, comment=None):
        sent.append((house_id, ga, value, comment))
        return {"request_id": "r1", "ga": ga, "value": value, "status": "sent"}

    async def boom_resolve(*_a, **_k):
        raise AssertionError("resolver must not run when ga is provided")

    monkeypatch.setattr(agent_actions, "_resolve_device_and_send", fake_send)
    monkeypatch.setattr(agent_actions, "resolve_objects", boom_resolve)

    out = asyncio.run(
        agent_actions.set_climate_setpoint(
            _session(obj),  # type: ignore[arg-type]
            "h1",
            query="кухня",
            setpoint_c=24.0,
            ga="1/6/7",
        )
    )
    assert sent == [("h1", "1/6/7", 24.0, "mcp set_climate кухня")]
    assert out["status"] == "sent"
    assert out["ga"] == "1/6/7"


def test_set_climate_by_ga_allows_1_6_prefix_without_role(monkeypatch) -> None:
    obj = _obj("1/6/12", "mystery", "other")
    sent: list[tuple] = []

    async def fake_send(session, house_id, ga, value, *, comment=None):
        sent.append((ga, value, comment))
        return {"request_id": "r1", "ga": ga, "value": value, "status": "sent"}

    monkeypatch.setattr(agent_actions, "_resolve_device_and_send", fake_send)
    out = asyncio.run(
        agent_actions.set_climate_setpoint(
            _session(obj),  # type: ignore[arg-type]
            "h1",
            setpoint_c=18.0,
            ga="1/6/12",
        )
    )
    assert sent == [("1/6/12", 18.0, "mcp set_climate 1/6/12")]
    assert out["ga"] == "1/6/12"


def test_set_climate_by_ga_rejects_non_setpoint() -> None:
    light = _obj("1/1/7", "Свет - кухня", "control,light")
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            agent_actions.set_climate_setpoint(
                _session(light),  # type: ignore[arg-type]
                "h1",
                setpoint_c=22.0,
                ga="1/1/7",
            )
        )
    assert ei.value.status_code == 400
    assert "not a climate setpoint" in ei.value.detail


def test_set_climate_by_ga_404_when_missing() -> None:
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            agent_actions.set_climate_setpoint(
                _session(None),  # type: ignore[arg-type]
                "h1",
                setpoint_c=22.0,
                ga="1/6/99",
            )
        )
    assert ei.value.status_code == 404


def test_set_climate_ambiguous_logs_and_returns_status(monkeypatch) -> None:
    matches = [
        ResolvedObject(
            ga="1/6/5",
            name="Уставка ТП - гостиная 1",
            tags=["setpoint", "heat"],
            role=ObjectRole.CLIMATE_SETPOINT,
            datatype=9,
        ),
        ResolvedObject(
            ga="1/6/6",
            name="Уставка ТП - гостиная 2",
            tags=["setpoint", "heat"],
            role=ObjectRole.CLIMATE_SETPOINT,
            datatype=9,
        ),
    ]

    async def fake_resolve(*_a, **_k):
        return ResolveResult(status="ambiguous", matches=matches)

    logged: list[tuple] = []

    def fake_warning(event, **kwargs):
        logged.append((event, kwargs))

    monkeypatch.setattr(agent_actions, "resolve_objects", fake_resolve)
    monkeypatch.setattr(agent_actions.logger, "warning", fake_warning)

    out = asyncio.run(
        agent_actions.set_climate_setpoint(
            None,  # type: ignore[arg-type]
            "h1",
            query="гостиная",
            setpoint_c=22.0,
        )
    )
    assert out["status"] == "ambiguous"
    assert {c["ga"] for c in out["candidates"]} == {"1/6/5", "1/6/6"}
    assert logged[0][0] == "set_climate_ambiguous"
    assert logged[0][1]["query"] == "гостиная"
    assert logged[0][1]["candidates"] == out["candidates"]
