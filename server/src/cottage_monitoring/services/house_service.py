"""House/device registry: auto-register, update last_seen, online/offline status."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import HOUSE_STATUS
from cottage_monitoring.models.device import Device
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


async def ensure_device(
    house_id: str, device_id: str, *, session: AsyncSession | None = None
) -> Device:
    """Auto-register device on first message; update last_seen."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        result = await session.execute(
            select(Device).where(Device.house_id == house_id, Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()

        if device is None:
            device = Device(
                house_id=house_id, device_id=device_id,
                is_active=True, online_status="unknown",
            )
            session.add(device)
            logger.info("device_auto_registered", house_id=house_id, device_id=device_id)

        device.last_seen = datetime.now(UTC)

        if own_session:
            await session.commit()

        return device
    finally:
        if own_session:
            await session.close()


async def handle_status(
    house_id: str, device_id: str, payload: dict, *, session: AsyncSession | None = None
) -> None:
    """Handle status/online message: update device online_status, then aggregate house."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        device = await ensure_device(house_id, device_id, session=session)
        status = payload.get("status", "unknown")
        device.online_status = status
        device.last_seen = datetime.now(UTC)

        logger.info("device_status_updated", house_id=house_id, device_id=device_id, status=status)

        await _aggregate_house_status(house_id, session=session)

        if own_session:
            await session.commit()
    finally:
        if own_session:
            await session.close()


async def _aggregate_house_status(
    house_id: str, *, session: AsyncSession
) -> None:
    """Recompute house online_status from its devices."""
    result = await session.execute(
        select(Device).where(Device.house_id == house_id, Device.is_active.is_(True))
    )
    devices = result.scalars().all()

    if not devices:
        aggregated = "unknown"
    elif all(d.online_status == "online" for d in devices):
        aggregated = "online"
    elif all(d.online_status == "offline" for d in devices):
        aggregated = "offline"
    else:
        aggregated = "partial"

    result = await session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    if house:
        house.online_status = aggregated
        house.last_seen = datetime.now(UTC)
        HOUSE_STATUS.labels(house_id=house_id).set(1.0 if aggregated == "online" else 0.0)


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
