"""Health check and Prometheus metrics endpoints."""

from __future__ import annotations

import time

import sqlalchemy
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest

from cottage_monitoring.db.session import engine
from cottage_monitoring.deps import mqtt_client, redis_cache

diagnostics_router = APIRouter(tags=["diagnostics"])

_start_time = time.monotonic()


@diagnostics_router.get("/health")
async def health() -> dict:
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    redis_ok = redis_cache.is_connected
    if redis_ok and redis_cache._client:
        try:
            await redis_cache._client.ping()
        except Exception:
            redis_ok = False

    return {
        "status": "healthy" if (db_ok and redis_ok and mqtt_client.is_connected) else "degraded",
        "mqtt_connected": mqtt_client.is_connected,
        "db_connected": db_ok,
        "redis_connected": redis_ok,
        "uptime_seconds": int(time.monotonic() - _start_time),
    }


@diagnostics_router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> bytes:
    return generate_latest()
