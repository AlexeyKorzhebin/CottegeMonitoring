"""Command service: send commands, handle ack, retry scheduler."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import COMMAND_LATENCY, COMMAND_SEND_TOTAL, COMMAND_TIMEOUT_TOTAL
from cottage_monitoring.models.command import Command
from cottage_monitoring.services.trace_service import record_trace

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

        now = datetime.now(UTC)

        was_timeout = cmd.status == "timeout"
        cmd.ts_ack = now
        cmd.status = ack_status
        cmd.results = payload.get("results")

        latency = (now - cmd.ts_sent).total_seconds()
        latency_ms = round(latency * 1000)
        COMMAND_LATENCY.labels(house_id=house_id).observe(latency)
        logger.info(
            "cmd_ack_applied",
            request_id=request_id_str,
            status=ack_status,
            latency_ms=latency_ms,
        )
        await record_trace(
            kind="command_ack",
            house_id=house_id,
            ref=request_id_str,
            duration_ms=latency_ms,
            status=ack_status,
            details={"device_id": cmd.device_id},
        )

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
            t_pub = time.perf_counter()
            await mqtt_client.publish(topic, json.dumps(mqtt_payload))
            publish_ms = round((time.perf_counter() - t_pub) * 1000)
            batch = "items" in mqtt_payload
            item_count = len(mqtt_payload["items"]) if batch else 1
            COMMAND_SEND_TOTAL.labels(house_id=house_id, batch=str(batch).lower()).inc()
            logger.info(
                "command_sent",
                request_id=str(request_id),
                house_id=house_id,
                device_id=device_id,
                batch=batch,
                item_count=item_count,
                publish_ms=publish_ms,
            )
            await record_trace(
                kind="command_sent",
                house_id=house_id,
                ref=str(request_id),
                duration_ms=publish_ms,
                status="sent",
                details={
                    "device_id": device_id,
                    "batch": batch,
                    "item_count": item_count,
                },
            )
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
