"""Tests for batch set_lights and zone query helpers."""

from __future__ import annotations

import asyncio

from cottage_monitoring.models.object import Object
from cottage_monitoring.services.object_resolver import ObjectRole, _is_zone_query, resolve_objects


def _obj(ga: str, name: str, tags: str) -> Object:
    return Object(
        house_id="h1",
        ga=ga,
        name=name,
        datatype=1001,
        tags=tags,
        is_active=True,
        is_timeseries=False,
    )


def test_is_zone_query_floor() -> None:
    assert _is_zone_query("1 этаж") is True
    assert _is_zone_query("свет на 2 этаже") is True
    assert _is_zone_query("уличное") is True
    assert _is_zone_query("кухня") is False


def test_set_lights_skips_unchanged(monkeypatch) -> None:
    from cottage_monitoring.services import agent_actions
    from cottage_monitoring.services import object_resolver

    a = _obj("1/1/7", "Свет - кухня", "1floor,control,light")
    b = _obj("1/1/9", "Свет - коридор", "1floor,control,light")

    async def fake_load(_session, _house_id: str) -> list[Object]:
        return [a, b]

    async def fake_states(_session, _house_id: str) -> dict[str, bool]:
        return {"1/1/7": True, "1/1/9": False}

    sent: list[dict] = []

    async def fake_batch(session, house_id, *, targets, value, comment):
        sent.append({"targets": targets, "value": value})
        return {"request_id": "r1", "status": "sent", "item_count": len(targets), "send_ms": 1}

    monkeypatch.setattr(object_resolver, "load_active_objects", fake_load)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)
    monkeypatch.setattr(agent_actions, "_send_light_batch", fake_batch)

    result = asyncio.run(
        agent_actions.set_lights(
            None,  # type: ignore[arg-type]
            "h1",
            query="1 этаж",
            on=False,
            skip_unchanged=True,
        )
    )
    assert result["status"] == "sent"
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["ga"] == "1/1/9"
    assert len(result["changed"]) == 1
    assert result["changed"][0]["ga"] == "1/1/7"
    assert sent[0]["targets"] == [("1/1/7", "Свет - кухня")]


def test_set_lights_ambiguous_non_zone(monkeypatch) -> None:
    from cottage_monitoring.services import agent_actions
    from cottage_monitoring.services import object_resolver

    async def fake_load(_session, _house_id: str) -> list[Object]:
        return [
            _obj("1/1/3", "Свет - гостиная", "control,light"),
            _obj("1/1/8", "Свет - гостиная торшер", "control,light"),
        ]

    async def fake_states(_session, _house_id: str) -> dict:
        return {}

    monkeypatch.setattr(object_resolver, "load_active_objects", fake_load)
    monkeypatch.setattr(agent_actions, "_get_state_map", fake_states)

    result = asyncio.run(
        agent_actions.set_lights(
            None,  # type: ignore[arg-type]
            "h1",
            query="гостиная торшер",
            on=False,
        )
    )
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2
