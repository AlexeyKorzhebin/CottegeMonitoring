"""House registry: auto-register, update last_seen, online/offline status."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import HOUSE_STATUS
from cottage_monitoring.models.house import House

logger = structlog.get_logger(__name__)


async def ensure_house(
    house_id: str, *, session: AsyncSession | None = None
) -> House:
    """Auto-register house on first message; update last_seen on any message."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        result = await session.execute(select(House).where(House.house_id == house_id))
        house = result.scalar_one_or_none()

        if house is None:
            house = House(house_id=house_id, is_active=True, online_status="unknown")
            session.add(house)
            logger.info("house_auto_registered", house_id=house_id)

        house.last_seen = datetime.now(UTC)

        if own_session:
            await session.commit()

        return house
    finally:
        if own_session:
            await session.close()


async def handle_status(
    house_id: str, payload: dict, *, session: AsyncSession | None = None
) -> None:
    """Handle status/online message: update online_status."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        house = await ensure_house(house_id, session=session)
        status = payload.get("status", "unknown")
        house.online_status = status
        house.last_seen = datetime.now(UTC)

        value = 1.0 if status == "online" else 0.0
        HOUSE_STATUS.labels(house_id=house_id).set(value)

        logger.info("house_status_updated", house_id=house_id, status=status)

        if own_session:
            await session.commit()
    finally:
        if own_session:
            await session.close()


async def is_house_active(
    house_id: str, *, session: AsyncSession | None = None
) -> bool:
    """Check if house is active (not deactivated by operator)."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        result = await session.execute(select(House).where(House.house_id == house_id))
        house = result.scalar_one_or_none()
        return house.is_active if house else True
    finally:
        if own_session:
            await session.close()
