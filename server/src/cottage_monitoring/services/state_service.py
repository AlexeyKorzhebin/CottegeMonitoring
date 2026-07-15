"""State service: upsert current_state + write-through Redis cache."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import LAG_SECONDS
from cottage_monitoring.models.state import CurrentState

logger = structlog.get_logger(__name__)


def storage_ga(ga: str) -> str:
    """Canonical GA for current_state / Redis: dash form matching MQTT state/ga topics."""
    return (ga or "").replace("/", "-")


def _ga_lookup_keys(ga: str) -> list[str]:
    """Both wire formats so we never fork duplicate current_state rows."""
    dash = storage_ga(ga)
    slash = dash.replace("-", "/")
    keys = [dash]
    if slash != dash:
        keys.append(slash)
    if ga and ga not in keys:
        keys.append(ga)
    return keys


def should_apply_state(existing_ts: datetime | None, incoming_ts: datetime) -> bool:
    """Apply incoming state only if it is not older than what we already have."""
    if existing_ts is None:
        return True
    if existing_ts.tzinfo is None:
        existing_ts = existing_ts.replace(tzinfo=UTC)
    if incoming_ts.tzinfo is None:
        incoming_ts = incoming_ts.replace(tzinfo=UTC)
    return incoming_ts >= existing_ts


async def _find_existing_state(
    session: AsyncSession, house_id: str, ga: str
) -> CurrentState | None:
    result = await session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id,
            CurrentState.ga.in_(_ga_lookup_keys(ga)),
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return None
    canonical = storage_ga(ga)
    for row in rows:
        if row.ga == canonical:
            return row
    return rows[0]


async def _write_redis(house_id: str, ga: str, cache_data: dict[str, Any]) -> None:
    try:
        from cottage_monitoring.deps import redis_cache

        if redis_cache.is_connected:
            await redis_cache.set_state(house_id, ga, cache_data)
    except Exception:
        logger.warning("redis_write_failed", house_id=house_id, ga=ga)


async def upsert_current_state(
    house_id: str,
    device_id: str,
    ga: str,
    *,
    ts_epoch: float | int,
    value: Any,
    datatype: int = 0,
    session: AsyncSession | None = None,
) -> bool:
    """Upsert current_state. Returns True if applied, False if skipped (older ts)."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        ga_key = storage_ga(ga)
        ts = datetime.fromtimestamp(float(ts_epoch or 0), tz=UTC)
        now = datetime.now(UTC)

        existing = await _find_existing_state(session, house_id, ga_key)
        if existing is not None and not should_apply_state(existing.ts, ts):
            logger.debug(
                "state_skipped_older_ts",
                house_id=house_id,
                ga=ga_key,
                existing_ts=existing.ts.isoformat() if existing.ts else None,
                incoming_ts=ts.isoformat(),
            )
            return False

        if existing is not None:
            existing.ga = ga_key
            existing.ts = ts
            existing.value = value
            existing.datatype = datatype
            existing.device_id = device_id
            existing.server_received_ts = now
        else:
            session.add(
                CurrentState(
                    house_id=house_id,
                    ga=ga_key,
                    device_id=device_id,
                    ts=ts,
                    value=value,
                    datatype=datatype,
                    server_received_ts=now,
                )
            )

        lag = time.time() - float(ts_epoch or 0)
        if lag > 0:
            LAG_SECONDS.labels(house_id=house_id).observe(lag)

        if own_session:
            await session.commit()

        await _write_redis(
            house_id,
            ga_key,
            {
                "ts": ts_epoch,
                "value": value,
                "datatype": datatype,
                "server_received_ts": now.isoformat(),
            },
        )
        return True
    finally:
        if own_session:
            await session.close()


async def handle_state(
    house_id: str,
    device_id: str,
    ga: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Upsert current_state for house_id+ga, write-through to Redis."""
    await upsert_current_state(
        house_id,
        device_id,
        ga,
        ts_epoch=payload.get("ts", 0) or 0,
        value=payload.get("value"),
        datatype=payload.get("datatype", 0) or 0,
        session=session,
    )


async def handle_states_batch(
    house_id: str,
    device_id: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Upsert batch of states from state/batch payload. Payload: {states: [{ga, ts, value, datatype}, ...]}."""
    states_list = payload.get("states")
    if not states_list or not isinstance(states_list, list):
        logger.warning("states_batch_empty_or_invalid", house_id=house_id)
        return

    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        for s in states_list:
            if not isinstance(s, dict):
                continue
            ga = s.get("ga")
            if not ga:
                continue
            await upsert_current_state(
                house_id,
                device_id,
                ga,
                ts_epoch=s.get("ts", 0) or 0,
                value=s.get("value"),
                datatype=s.get("datatype", 0) or 0,
                session=session,
            )

        if own_session:
            await session.commit()
    finally:
        if own_session:
            await session.close()
