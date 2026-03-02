"""Tests for application lifespan: startup, health check, degraded mode."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


async def test_startup_connects_all_services() -> None:
    """LifespanManager → /health shows mqtt, db, redis connected."""
    from cottage_monitoring.main import app

    async with LifespanManager(app, startup_timeout=15) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(30):
                r = await client.get("/health")
                if r.status_code == 200 and r.json().get("mqtt_connected"):
                    break
                await asyncio.sleep(0.5)

            assert r.status_code == 200
            body = r.json()
            assert body["db_connected"] is True
            assert body["redis_connected"] is True
            assert body["mqtt_connected"] is True
            assert body["status"] == "healthy"


async def test_health_reports_uptime() -> None:
    """After startup, uptime_seconds >= 0."""
    from cottage_monitoring.main import app

    async with LifespanManager(app, startup_timeout=15) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(30):
                r = await client.get("/health")
                if r.status_code == 200 and r.json().get("mqtt_connected"):
                    break
                await asyncio.sleep(0.5)

            body = r.json()
            assert body["uptime_seconds"] >= 0


async def test_startup_mqtt_unavailable_degraded() -> None:
    """App starts even when MQTT broker is unreachable — status is 'degraded'."""
    from cottage_monitoring.main import app

    with patch("cottage_monitoring.deps.mqtt_client._host", "unreachable-host-12345"):
        async with LifespanManager(app, startup_timeout=10) as manager:
            transport = ASGITransport(app=manager.app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await asyncio.sleep(2)
                r = await client.get("/health")
                assert r.status_code == 200
                body = r.json()
                assert body["mqtt_connected"] is False
                assert body["status"] == "degraded"
                assert body["db_connected"] is True
