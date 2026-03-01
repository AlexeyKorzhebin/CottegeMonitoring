"""Integration tests for house lifecycle: auto-create, deactivate, reactivate."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cottage_monitoring.models.house import House
from cottage_monitoring.models.state import CurrentState
from cottage_monitoring.services.house_service import ensure_house, is_house_active

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from cottage_monitoring.services.state_service import handle_state

pytestmark = pytest.mark.integration


async def test_auto_create_on_first_message(db_session: AsyncSession) -> None:
    """ensure_house for new ID → creates house with is_active=True, online_status='unknown'."""
    house_id = "house-lifecycle-new"
    house = await ensure_house(house_id, session=db_session)
    await db_session.commit()

    assert house.is_active is True
    assert house.online_status == "unknown"

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.is_active is True
    assert row.online_status == "unknown"


async def test_deactivate_house(db_session: AsyncSession) -> None:
    """Set house.is_active = False → is_house_active returns False."""
    house_id = "house-lifecycle-deactivate"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    assert house is not None
    house.is_active = False
    await db_session.commit()
    await db_session.refresh(house)

    assert await is_house_active(house_id, session=db_session) is False


async def test_reactivate_house(db_session: AsyncSession) -> None:
    """Set is_active=False then True → is_house_active returns True."""
    house_id = "house-lifecycle-reactivate"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    assert house is not None

    house.is_active = False
    await db_session.commit()

    house.is_active = True
    await db_session.commit()

    assert await is_house_active(house_id, session=db_session) is True


async def test_data_preserved_after_deactivation(db_session: AsyncSession) -> None:
    """Create house + state, deactivate → state data still in DB."""
    house_id = "house-lifecycle-preserve"
    ga = "1/1/1"
    await ensure_house(house_id, session=db_session)
    await handle_state(
        house_id,
        ga,
        {"ts": 1730000000, "value": True, "datatype": 1001},
        session=db_session,
    )
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    assert house is not None
    house.is_active = False
    await db_session.commit()

    result = await db_session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id, CurrentState.ga == ga
        )
    )
    state = result.scalar_one_or_none()
    assert state is not None
    assert state.value is True
