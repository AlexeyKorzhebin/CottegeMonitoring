"""Integration tests for events ingestion: MQTT events → append to events table."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.event import Event
from cottage_monitoring.services.event_service import handle_event

pytestmark = pytest.mark.integration

SAMPLE_EVENT_PAYLOAD = {
    "ts": 1730000000,
    "seq": 1,
    "type": "knx.groupwrite",
    "ga": "1/1/1",
    "id": 2305,
    "name": "Свет",
    "datatype": 1001,
    "value": True,
}


async def test_event_append(db_session: AsyncSession) -> None:
    """Event is inserted into events table with all fields."""
    house_id = "house-event-append"
    await handle_event(house_id, "lm-main", SAMPLE_EVENT_PAYLOAD, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Event)
        .where(Event.house_id == house_id)
        .order_by(Event.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.ts is not None
    assert row.seq == 1
    assert row.type == "knx.groupwrite"
    assert row.ga == "1/1/1"
    assert row.object_id == 2305
    assert row.name == "Свет"
    assert row.datatype == 1001
    assert row.value is True


async def test_event_duplicate_accepted(db_session: AsyncSession) -> None:
    """Same event twice → both rows saved (no unique constraint, QoS 1 duplicates OK)."""
    house_id = "house-event-dup"
    result_before = await db_session.execute(
        select(func.count()).select_from(Event).where(Event.house_id == house_id)
    )
    count_before = result_before.scalar_one()
    await handle_event(house_id, "lm-main", SAMPLE_EVENT_PAYLOAD, session=db_session)
    await handle_event(house_id, "lm-main", SAMPLE_EVENT_PAYLOAD, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(func.count()).select_from(Event).where(Event.house_id == house_id)
    )
    count = result.scalar_one()
    assert count == count_before + 2


async def test_event_server_received_ts(db_session: AsyncSession) -> None:
    """server_received_ts is populated."""
    house_id = "house-event-ts"
    await handle_event(house_id, "lm-main", SAMPLE_EVENT_PAYLOAD, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Event)
        .where(Event.house_id == house_id)
        .order_by(Event.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.server_received_ts is not None


async def test_event_raw_json_saved(db_session: AsyncSession) -> None:
    """Full raw JSON is preserved."""
    house_id = "house-event-raw"
    payload = {**SAMPLE_EVENT_PAYLOAD, "extra_field": "preserved"}
    await handle_event(house_id, "lm-main", payload, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Event)
        .where(Event.house_id == house_id)
        .order_by(Event.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.raw_json == payload
    assert row.raw_json.get("extra_field") == "preserved"
