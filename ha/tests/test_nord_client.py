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
