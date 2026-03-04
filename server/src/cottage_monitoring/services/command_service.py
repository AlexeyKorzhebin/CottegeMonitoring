"""Command service: send commands, handle ack, retry scheduler."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import COMMAND_LATENCY, COMMAND_TIMEOUT_TOTAL
from cottage_monitoring.models.command import Command

logger = structlog.get_logger(__name__)


async def handle_ack(
    house_id: str,
    request_id_str: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Handle cmd/ack — update command status in DB."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        try:
            request_id = uuid.UUID(request_id_str)
        except ValueError:
            logger.warning("invalid_request_id", request_id=request_id_str)
            return

        result = await session.execute(
            select(Command).where(Command.request_id == request_id)
        )
        cmd = result.scalar_one_or_none()
        if cmd is None:
            logger.info("ack_for_unknown_command", request_id=request_id_str, house_id=house_id)
            return

        ack_status = payload.get("status", "ok")
        logger.info("cmd_ack_applied", request_id=request_id_str, status=ack_status)

        now = datetime.now(UTC)

        was_timeout = cmd.status == "timeout"
        cmd.ts_ack = now
        cmd.status = ack_status
        cmd.results = payload.get("results")

        latency = (now - cmd.ts_sent).total_seconds()
        COMMAND_LATENCY.labels(house_id=house_id).observe(latency)

        if was_timeout:
            logger.info("late_ack_received", request_id=request_id_str, status=ack_status)

        if own_session:
            await session.commit()

    finally:
        if own_session:
            await session.close()


async def send_command(
    house_id: str,
    device_id: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> Command:
    """Create command record and publish to MQTT."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        request_id = uuid.uuid4()
        now = datetime.now(UTC)

        mqtt_payload = {**payload, "request_id": str(request_id)}

        cmd = Command(
            request_id=request_id,
            house_id=house_id,
            device_id=device_id,
            ts_sent=now,
            payload=mqtt_payload,
            status="sent",
        )
        session.add(cmd)

        if own_session:
            await session.commit()

        # Publish to MQTT
        try:
            import json

            from cottage_monitoring.config import settings
            from cottage_monitoring.deps import mqtt_client

            topic = f"{settings.mqtt_topic_prefix}cm/{house_id}/{device_id}/v1/cmd"
            await mqtt_client.publish(topic, json.dumps(mqtt_payload))
        except Exception:
            logger.exception("mqtt_publish_failed", house_id=house_id, device_id=device_id, request_id=str(request_id))

        return cmd

    finally:
        if own_session:
            await session.close()


async def retry_pending_commands(
    *,
    session: AsyncSession | None = None,
) -> None:
    """Check for timed-out commands and retry or mark as timeout."""
    from cottage_monitoring.config import settings

    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        result = await session.execute(
            select(Command).where(Command.status == "sent")
        )
        commands = result.scalars().all()

        now = datetime.now(UTC)
        for cmd in commands:
            elapsed = (now - cmd.ts_sent).total_seconds()
            if elapsed < settings.cmd_timeout_seconds:
                continue

            if cmd.retry_count < settings.cmd_max_retries:
                cmd.retry_count += 1
                cmd.ts_sent = now

                try:
                    import json

                    from cottage_monitoring.deps import mqtt_client

                    topic = f"{settings.mqtt_topic_prefix}cm/{cmd.house_id}/{cmd.device_id}/v1/cmd"
                    await mqtt_client.publish(topic, json.dumps(cmd.payload))
                    logger.info(
                        "command_retried",
                        request_id=str(cmd.request_id),
                        retry=cmd.retry_count,
                    )
                except Exception:
                    logger.exception("retry_publish_failed", request_id=str(cmd.request_id))
            else:
                cmd.status = "timeout"
                COMMAND_TIMEOUT_TOTAL.labels(house_id=cmd.house_id).inc()
                logger.warning("command_timeout", request_id=str(cmd.request_id))

        if own_session:
            await session.commit()
    finally:
        if own_session:
            await session.close()
