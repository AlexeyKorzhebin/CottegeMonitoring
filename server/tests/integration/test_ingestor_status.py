"""Integration tests for online/offline status handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cottage_monitoring.models.house import House

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from cottage_monitoring.services.house_service import ensure_house, handle_status

pytestmark = pytest.mark.integration


async def test_status_online(db_session: AsyncSession) -> None:
    """handle_status with online → house.online_status == 'online'."""
    house_id = "house-status-online"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_status(
        house_id,
        {"ts": 1730000000, "status": "online"},
        session=db_session,
    )
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    assert house is not None
    assert house.online_status == "online"


async def test_lwt_offline(db_session: AsyncSession) -> None:
    """handle_status with offline → house.online_status == 'offline'."""
    house_id = "house-status-offline"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_status(
        house_id,
        {"ts": 1730000000, "status": "offline"},
        session=db_session,
    )
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    assert house is not None
    assert house.online_status == "offline"


async def test_unknown_house_auto_created(db_session: AsyncSession) -> None:
    """handle_status for new house_id → house auto-created with is_active=True."""
    house_id = "house-auto-created-via-status"
    await handle_status(
        house_id,
        {"ts": 1730000000, "status": "online"},
        session=db_session,
    )
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    assert house is not None
    assert house.is_active is True
    assert house.online_status == "online"
