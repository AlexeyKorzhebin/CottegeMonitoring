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
