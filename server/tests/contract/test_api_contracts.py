"""Contract tests: API endpoints match contracts (HTTP status, response structure)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.contract


async def test_health_endpoint(async_client: AsyncClient) -> None:
    """GET /health → 200, response has status, mqtt_connected, db_connected, redis_connected, uptime_seconds."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "mqtt_connected" in data
    assert "db_connected" in data
    assert "redis_connected" in data
    assert "uptime_seconds" in data


async def test_houses_list(async_client: AsyncClient) -> None:
    """GET /api/v1/houses → 200, response has items list and total int."""
    resp = await async_client.get("/api/v1/houses")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data
    assert isinstance(data["total"], int)


async def test_house_not_found(async_client: AsyncClient) -> None:
    """GET /api/v1/houses/nonexistent → 404."""
    resp = await async_client.get("/api/v1/houses/nonexistent")
    assert resp.status_code == 404


async def test_events_list(async_client: AsyncClient) -> None:
    """GET /api/v1/houses/house-01/events?from=2026-01-01T00:00:00Z → 200, response has items, total, limit, offset."""
    resp = await async_client.get(
        "/api/v1/houses/house-01/events",
        params={"from": "2026-01-01T00:00:00Z"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


async def test_state_list(async_client: AsyncClient) -> None:
    """GET /api/v1/houses/house-01/state → 200, response has items and total."""
    resp = await async_client.get("/api/v1/houses/house-01/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


async def test_objects_list(async_client: AsyncClient) -> None:
    """GET /api/v1/houses/house-01/objects → 200, response has items and total."""
    resp = await async_client.get("/api/v1/houses/house-01/objects")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


async def test_commands_list(async_client: AsyncClient) -> None:
    """GET /api/v1/houses/house-01/commands → 200, response has items, total, limit, offset."""
    resp = await async_client.get("/api/v1/houses/house-01/commands")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


async def test_metrics_endpoint(async_client: AsyncClient) -> None:
    """GET /metrics → 200, content type text/plain."""
    resp = await async_client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")


async def test_create_command_validation(async_client: AsyncClient) -> None:
    """POST /api/v1/houses/nonexistent/commands with body {"ga": "1/1/1", "value": true} → 400 (house not found)."""
    resp = await async_client.post(
        "/api/v1/houses/nonexistent/commands",
        json={"ga": "1/1/1", "value": True},
    )
    assert resp.status_code == 400
