"""Event service: append events to TimescaleDB."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import LAG_CURRENT, LAG_SECONDS
from cottage_monitoring.models.event import Event
from cottage_monitoring.utils.ga import ga_to_slash

logger = structlog.get_logger(__name__)


def _observe_lag(house_id: str, ts_epoch: float) -> None:
    lag = time.time() - (ts_epoch or 0)
    if lag > 0:
        LAG_SECONDS.labels(house_id=house_id).observe(lag)
        LAG_CURRENT.labels(house_id=house_id).set(lag)


async def _insert_event(
    session: AsyncSession,
    *,
    house_id: str,
    device_id: str,
    ts: datetime,
    seq: int | None,
    type_: str | None,
    ga: str | None,
    object_id: int | None,
    name: str | None,
    datatype: int | None,
    value,
    raw_json: dict,
    server_received_ts: datetime,
) -> None:
    values = dict(
        house_id=house_id,
        device_id=device_id,
        ts=ts,
        seq=seq,
        type=type_,
        ga=ga,
        object_id=object_id,
        name=name,
        datatype=datatype,
        value=value,
        raw_json=raw_json,
        server_received_ts=server_received_ts,
    )
    if seq is not None:
        stmt = (
            insert(Event)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["house_id", "device_id", "seq", "ts"],
                index_where=text("seq IS NOT NULL"),
            )
        )
        await session.execute(stmt)
    else:
        session.add(Event(**values))


async def handle_event(
    house_id: str,
    device_id: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Append event to events table (all fields + raw_json + server_received_ts).

    Also mirrors value into current_state so agents stay fresh even if retained
    MQTT state/ga topics are stale or state/batch was lost (QoS 0 events still land).
    QoS1 duplicates (same house/device/seq/ts) are ignored via unique index.
    """
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        ts_epoch = payload.get("ts", 0)
        ts = datetime.fromtimestamp(ts_epoch, tz=UTC)
        now = datetime.now(UTC)
        ga_raw = payload.get("ga")
        ga = ga_to_slash(ga_raw) if ga_raw is not None else None

        await _insert_event(
            session,
            house_id=house_id,
            device_id=device_id,
            ts=ts,
            seq=payload.get("seq"),
            type_=payload.get("type"),
            ga=ga,
            object_id=payload.get("id"),
            name=payload.get("name"),
            datatype=payload.get("datatype"),
            value=payload.get("value"),
            raw_json=payload,
            server_received_ts=now,
        )

        _observe_lag(house_id, ts_epoch)

        if ga is not None and "value" in payload:
            from cottage_monitoring.services.state_service import upsert_current_state

            await upsert_current_state(
                house_id,
                device_id,
                ga,
                ts_epoch=ts_epoch or 0,
                value=payload.get("value"),
                datatype=payload.get("datatype", 0) or 0,
                session=session,
            )

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
            ga_raw = evt.get("ga")
            ga = ga_to_slash(ga_raw) if ga_raw is not None else None
            await _insert_event(
                session,
                house_id=house_id,
                device_id=device_id,
                ts=ts,
                seq=evt.get("seq"),
                type_=evt.get("type"),
                ga=ga,
                object_id=evt.get("id"),
                name=evt.get("name"),
                datatype=evt.get("datatype"),
                value=evt.get("value"),
                raw_json=evt,
                server_received_ts=now,
            )
            _observe_lag(house_id, ts_epoch)

            if ga is not None and "value" in evt:
                from cottage_monitoring.services.state_service import upsert_current_state

                await upsert_current_state(
                    house_id,
                    device_id,
                    ga,
                    ts_epoch=ts_epoch or 0,
                    value=evt.get("value"),
                    datatype=evt.get("datatype", 0) or 0,
                    session=session,
                )

        if own_session:
            await session.commit()

    finally:
        if own_session:
            await session.close()
