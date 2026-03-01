"""Shared test fixtures: testcontainers, async DB session, httpx client."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cottage_monitoring.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create a PostgreSQL+TimescaleDB test engine via testcontainers."""
    try:
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer(
            image="timescale/timescaledb:latest-pg16",
            username="test",
            password="test",
            dbname="test_db",
        )
        container.start()
        url = container.get_connection_url().replace("psycopg2", "asyncpg")
        engine = create_async_engine(url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        await engine.dispose()
        container.stop()
    except ImportError:
        pytest.skip("testcontainers not available")


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(db_engine) -> AsyncGenerator[AsyncClient]:
    """httpx AsyncClient wired to the FastAPI app with test DB."""
    from cottage_monitoring import main

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def redis_client():
    """Create a test Redis connection via testcontainers."""
    try:
        from testcontainers.redis import RedisContainer

        container = RedisContainer()
        container.start()
        import redis.asyncio as aioredis

        url = f"redis://localhost:{container.get_exposed_port(6379)}/0"
        client = aioredis.Redis.from_url(url, decode_responses=True)
        yield client
        await client.aclose()
        container.stop()
    except ImportError:
        pytest.skip("testcontainers not available")
