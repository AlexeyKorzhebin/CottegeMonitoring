"""FastAPI application with async lifespan: DB, Redis, MQTT subscriber."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from cottage_monitoring.config import settings
from cottage_monitoring.db.session import engine
from cottage_monitoring.deps import mqtt_client, redis_cache
from cottage_monitoring.logging_config import setup_logging

logger = structlog.get_logger(__name__)


async def _command_retry_loop() -> None:
    """Periodically check for timed-out commands and retry."""
    from cottage_monitoring.services.command_service import retry_pending_commands

    while True:
        try:
            await retry_pending_commands()
        except Exception:
            logger.exception("command_retry_error")
        await asyncio.sleep(10)


async def _mqtt_loop() -> None:
    from cottage_monitoring.services.ingestor import handle_message

    mqtt_client.subscribe(settings.mqtt_subscription_topic)
    async for message in mqtt_client.messages():
        try:
            await handle_message(message)
        except Exception:
            logger.exception("unhandled_ingestor_error", topic=str(message.topic))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info("starting", env=settings.env, mqtt_topic=settings.mqtt_subscription_topic)

    await redis_cache.connect()

    mqtt_task = asyncio.create_task(_mqtt_loop())
    retry_task = asyncio.create_task(_command_retry_loop())

    yield

    logger.info("shutting_down")
    await mqtt_client.disconnect()
    for task in (mqtt_task, retry_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await redis_cache.disconnect()
    await engine.dispose()


app = FastAPI(
    title="CottageMonitoring",
    version="0.1.0",
    lifespan=lifespan,
)

from cottage_monitoring.api.diagnostics import diagnostics_router  # noqa: E402
from cottage_monitoring.api.router import api_router  # noqa: E402

app.include_router(api_router, prefix="/api/v1")
app.include_router(diagnostics_router)
