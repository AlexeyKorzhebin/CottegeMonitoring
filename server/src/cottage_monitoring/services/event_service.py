"""Event service: append events to TimescaleDB."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import LAG_SECONDS
from cottage_monitoring.models.event import Event

logger = structlog.get_logger(__name__)


async def handle_event(
    house_id: str,
    device_id: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Append event to events table (all fields + raw_json + server_received_ts)."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        ts_epoch = payload.get("ts", 0)
        ts = datetime.fromtimestamp(ts_epoch, tz=UTC)
        now = datetime.now(UTC)

        event = Event(
            house_id=house_id,
            device_id=device_id,
            ts=ts,
            seq=payload.get("seq"),
            type=payload.get("type"),
            ga=payload.get("ga"),
            object_id=payload.get("id"),
            name=payload.get("name"),
            datatype=payload.get("datatype"),
            value=payload.get("value"),
            raw_json=payload,
            server_received_ts=now,
        )
        session.add(event)

        lag = time.time() - ts_epoch
        if lag > 0:
            LAG_SECONDS.labels(house_id=house_id).observe(lag)

        if own_session:
            await session.commit()

    finally:
        if own_session:
            await session.close()


async def handle_events_batch(
    house_id: str,
    device_id: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Append batch of events from events/batch topic. Payload: {events: [{...}, ...]}."""
    events_data = payload.get("events")
    if not isinstance(events_data, list) or len(events_data) == 0:
        logger.warning("invalid_events_batch", house_id=house_id, has_events=bool(events_data))
        return

    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        now = datetime.now(UTC)
        for evt in events_data:
            if not isinstance(evt, dict):
                continue
            ts_epoch = evt.get("ts", 0)
            ts = datetime.fromtimestamp(ts_epoch, tz=UTC)
            event = Event(
                house_id=house_id,
                device_id=device_id,
                ts=ts,
                seq=evt.get("seq"),
                type=evt.get("type"),
                ga=evt.get("ga"),
                object_id=evt.get("id"),
                name=evt.get("name"),
                datatype=evt.get("datatype"),
                value=evt.get("value"),
                raw_json=evt,
                server_received_ts=now,
            )
            session.add(event)
            lag = time.time() - ts_epoch
            if lag > 0:
                LAG_SECONDS.labels(house_id=house_id).observe(lag)

        if own_session:
            await session.commit()
        logger.debug("events_batch_processed", house_id=house_id, count=len(events_data))
    finally:
        if own_session:
            await session.close()
