"""State service: upsert current_state + write-through Redis cache."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import LAG_SECONDS
from cottage_monitoring.models.state import CurrentState

logger = structlog.get_logger(__name__)


async def handle_state(
    house_id: str,
    device_id: str,
    ga: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Upsert current_state for house_id+ga, write-through to Redis."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        ts_epoch = payload.get("ts", 0)
        ts = datetime.fromtimestamp(ts_epoch, tz=UTC)
        value = payload.get("value")
        datatype = payload.get("datatype", 0)
        now = datetime.now(UTC)

        result = await session.execute(
            select(CurrentState).where(
                CurrentState.house_id == house_id, CurrentState.ga == ga
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.ts = ts
            existing.value = value
            existing.datatype = datatype
            existing.device_id = device_id
            existing.server_received_ts = now
        else:
            state = CurrentState(
                house_id=house_id,
                ga=ga,
                device_id=device_id,
                ts=ts,
                value=value,
                datatype=datatype,
                server_received_ts=now,
            )
            session.add(state)

        # Prometheus lag metric
        lag = time.time() - ts_epoch
        if lag > 0:
            LAG_SECONDS.labels(house_id=house_id).observe(lag)

        if own_session:
            await session.commit()

        # Write-through to Redis (best-effort)
        try:
            from cottage_monitoring.deps import redis_cache

            if redis_cache.is_connected:
                cache_data = {
                    "ts": ts_epoch,
                    "value": value,
                    "datatype": datatype,
                    "server_received_ts": now.isoformat(),
                }
                await redis_cache.set_state(house_id, ga, cache_data)
        except Exception:
            logger.warning("redis_write_failed", house_id=house_id, ga=ga)

    finally:
        if own_session:
            await session.close()
