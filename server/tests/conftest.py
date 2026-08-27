"""Shared test fixtures: use server DB, Redis, MQTT via env (SSH tunnel required)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

# Load .env.test for integration/contract tests (use server DB via SSH tunnel).
# Set COTTAGE_USE_SERVER_FOR_TESTS=0 to skip (e.g. for unit config default tests).
_env_test = Path(__file__).resolve().parent.parent / ".env.test"
if _env_test.exists() and os.environ.get("COTTAGE_USE_SERVER_FOR_TESTS") != "0":
    from dotenv import load_dotenv
    load_dotenv(_env_test)

# Tests must not write operation_traces to the shared dev DB. It also keeps unit
# tests off the connection pool: record_trace() opens its own session, and one
# opened from an asyncio.run() loop poisons the pool for later async tests.
os.environ.setdefault("TRACE_PERSIST", "false")

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.deps import redis_cache


@pytest.fixture(autouse=True)
def _keep_session_event_loop():
    """Restore the loop that asyncio.run() clears.

    Unit tests drive coroutines with asyncio.run(), which sets the current event
    loop to None on exit. pytest-asyncio's session-scoped loop is looked up via
    asyncio.get_event_loop(), so without this every async test that runs after a
    unit test in the same process fails with "no current event loop".
    """
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        loop = None
    yield
    if loop is not None and not loop.is_closed():
        asyncio.set_event_loop(loop)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Session from app's engine (server DB via env). Each test uses unique house_ids."""
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient]:
    """httpx AsyncClient wired to FastAPI app (uses server DB/Redis/MQTT from env)."""
    from cottage_monitoring.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def mqtt_app_client() -> AsyncGenerator[AsyncClient]:
    """
    AsyncClient with app lifespan running (MQTT subscriber connected).
    Use for full-path tests: publish to MQTT → ingestor → DB.
    """
    from asgi_lifespan import LifespanManager
    from cottage_monitoring.main import app

    from cottage_monitoring.deps import mqtt_client as _mc
    _mc._shutdown = False
    _mc._connected = False
    _mc._backoff = 1.0

    async with LifespanManager(app, startup_timeout=15) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(30):
                r = await client.get("/health")
                if r.status_code == 200 and r.json().get("mqtt_connected"):
                    break
                await asyncio.sleep(0.5)
            yield client


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _connect_services() -> AsyncGenerator[None]:
    """Connect Redis for integration tests (state_service writes to cache). MQTT connects per-publish."""
    await redis_cache.connect()
    try:
        yield
    finally:
        await redis_cache.disconnect()

