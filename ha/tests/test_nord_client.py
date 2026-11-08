# ha/tests/test_nord_client.py
from __future__ import annotations

import asyncio

import pytest

from cottage_monitoring.nord_client import NordClient, NordError


class Fake:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self.payload = payload
        self.calls: list = []

    async def __call__(self, method, url, headers, json):
        self.calls.append((method, url, headers, json))
        return self.status, self.payload


def test_call_op_posts_house_path_with_api_key() -> None:
    fake = Fake(200, {"items": []})
    client = NordClient(
        "http://127.0.0.1:8321/api/v1", "cm_secret", "house", transport=fake
    )

    async def _run() -> None:
        await client.call_op("list_lights", {})

    asyncio.run(_run())
    method, url, headers, body = fake.calls[0]
    assert method == "POST"
    assert url == "http://127.0.0.1:8321/api/v1/houses/house/ops/list_lights"
    assert headers["X-API-Key"] == "cm_secret"
    assert body == {}


def test_401_raises_nord_error() -> None:
    client = NordClient(
        "http://x/api/v1", "bad", "house", transport=Fake(401, {"detail": "no"})
    )

    async def _run() -> None:
        await client.call_op("list_lights")

    with pytest.raises(NordError) as ei:
        asyncio.run(_run())
    assert ei.value.status == 401


def test_404_raises_nord_error() -> None:
    client = NordClient(
        "http://x/api/v1", "key", "house", transport=Fake(404, {"detail": "missing"})
    )

    async def _run() -> None:
        await client.call_op("set_kettle", {"setpoint_c": 80})

    with pytest.raises(NordError) as ei:
        asyncio.run(_run())
    assert ei.value.status == 404


def test_200_with_ambiguous_status_raises_nord_error() -> None:
    payload = {
        "status": "ambiguous",
        "candidates": [
            {"name": "Уставка ТП - гостиная 1", "ga": "1/6/5"},
            {"name": "Уставка ТП - гостиная 2", "ga": "1/6/6"},
        ],
    }
    client = NordClient(
        "http://x/api/v1", "key", "house", transport=Fake(200, payload)
    )

    async def _run() -> None:
        await client.call_op("set_climate", {"query": "гостиная", "setpoint_c": 22})

    with pytest.raises(NordError) as ei:
        asyncio.run(_run())
    assert ei.value.status == 409
    assert "ambiguous" in ei.value.body


def test_200_with_not_found_status_raises_nord_error() -> None:
    client = NordClient(
        "http://x/api/v1",
        "key",
        "house",
        transport=Fake(200, {"status": "not_found"}),
    )

    async def _run() -> None:
        await client.call_op("set_climate", {"query": "нет такой", "setpoint_c": 22})

    with pytest.raises(NordError) as ei:
        asyncio.run(_run())
    assert ei.value.status == 409


def test_200_sent_status_returns_payload() -> None:
    payload = {"status": "sent", "ga": "1/6/7", "request_id": "r1"}
    client = NordClient(
        "http://x/api/v1", "key", "house", transport=Fake(200, payload)
    )

    async def _run() -> dict:
        return await client.call_op("set_climate", {"ga": "1/6/7", "setpoint_c": 22})

    assert asyncio.run(_run()) == payload


def test_get_sensors_200_ambiguous_with_items_returns_payload() -> None:
    payload = {
        "status": "ambiguous",
        "items": [
            {"name": "Влажность - гостиная 1", "ga": "1/2/1", "value": 45.0},
            {"name": "Влажность - гостиная 2", "ga": "1/2/2", "value": 47.0},
        ],
    }
    client = NordClient(
        "http://x/api/v1", "key", "house", transport=Fake(200, payload)
    )

    async def _run() -> dict:
        return await client.call_op("get_sensors")

    assert asyncio.run(_run()) == payload


def test_get_climate_200_ok_returns_payload() -> None:
    payload = {
        "status": "ok",
        "zones": [{"name": "Гостиная", "setpoint_c": 22.0, "current_c": 21.5}],
    }
    client = NordClient(
        "http://x/api/v1", "key", "house", transport=Fake(200, payload)
    )

    async def _run() -> dict:
        return await client.call_op("get_climate")

    assert asyncio.run(_run()) == payload
