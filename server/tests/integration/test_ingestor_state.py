"""Integration tests for state ingestion: MQTT state/ga/* → current_state upsert + Redis cache."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.house import House
from cottage_monitoring.models.state import CurrentState
from cottage_monitoring.services.house_service import ensure_house
from cottage_monitoring.services.state_service import handle_state

pytestmark = pytest.mark.integration

SAMPLE_PAYLOAD = {"ts": 1730000000, "value": True, "datatype": 1001}


async def test_state_upsert_new(db_session: AsyncSession) -> None:
    """First state for a GA → insert into current_state."""
    house_id = "house-state-new"
    ga = "1/1/1"
    await ensure_house(house_id, session=db_session)
    await handle_state(house_id, "lm-main", ga, SAMPLE_PAYLOAD, session=db_session)
    await db_session.commit()

    house = await db_session.get(House, house_id)
    assert house is not None

    result = await db_session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id, CurrentState.ga == ga
        )
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.value is True
    assert row.datatype == 1001
    assert row.ts is not None


async def test_state_upsert_existing(db_session: AsyncSession) -> None:
    """Second state for same GA → update value + ts."""
    house_id = "house-state-update"
    ga = "1/2/3"
    await ensure_house(house_id, session=db_session)
    await handle_state(house_id, "lm-main", ga, SAMPLE_PAYLOAD, session=db_session)
    await db_session.commit()

    payload2 = {"ts": 1730000100, "value": False, "datatype": 1001}
    await handle_state(house_id, "lm-main", ga, payload2, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id, CurrentState.ga == ga
        )
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.value is False
    assert row.ts is not None


async def test_state_server_received_ts(db_session: AsyncSession) -> None:
    """Verify server_received_ts is populated."""
    house_id = "house-state-ts"
    ga = "2/1/1"
    await ensure_house(house_id, session=db_session)
    await handle_state(house_id, "lm-main", ga, SAMPLE_PAYLOAD, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id, CurrentState.ga == ga
        )
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.server_received_ts is not None


async def test_state_multiple_gas(db_session: AsyncSession) -> None:
    """State for different GAs stored independently."""
    house_id = "house-state-multi"
    await ensure_house(house_id, session=db_session)

    await handle_state(house_id, "lm-main", "1/1/1", SAMPLE_PAYLOAD, session=db_session)
    payload2 = {"ts": 1730000000, "value": 21.5, "datatype": 9001}
    await handle_state(house_id, "lm-main", "1/3/1", payload2, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(CurrentState).where(CurrentState.house_id == house_id)
    )
    rows = result.scalars().all()
    assert len(rows) == 2

    ga_values = {(r.ga, r.value) for r in rows}
    assert ("1/1/1", True) in ga_values
    assert ("1/3/1", 21.5) in ga_values
