"""House/device registry: auto-register, update last_seen, online/offline status."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.config import settings
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

        await _aggregate_house_status(house_id, session=session, touch_last_seen=True)

        if own_session:
            await session.commit()
    finally:
        if own_session:
            await session.close()


async def mark_stale_devices_offline(
    *,
    session: AsyncSession | None = None,
    now: datetime | None = None,
    stale_after: timedelta | None = None,
    house_id: str | None = None,
) -> int:
    """Mark active devices offline when their last MQTT message is too old.

    ``last_seen`` is left as the real last contact. ``house_id`` limits the
    update (tests); the background loop omits it and sweeps every house.
    """
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        moment = now or datetime.now(UTC)
        window = (
            stale_after
            if stale_after is not None
            else timedelta(seconds=settings.device_offline_after_seconds)
        )
        cutoff = moment - window
        conditions = [
            Device.is_active.is_(True),
            Device.online_status == "online",
            or_(Device.last_seen.is_(None), Device.last_seen < cutoff),
        ]
        if house_id is not None:
            conditions.append(Device.house_id == house_id)

        result = await session.execute(
            update(Device)
            .where(*conditions)
            .values(online_status="offline")
            .returning(Device.house_id, Device.device_id)
        )
        rows = result.all()
        affected: dict[str, list[str]] = {}
        for row in rows:
            affected.setdefault(row.house_id, []).append(row.device_id)
            # Core UPDATE does not refresh the identity map; drop stale "online".
            loaded = await session.get(Device, (row.house_id, row.device_id))
            if loaded is not None:
                session.expire(loaded)

        for hid, device_ids in affected.items():
            logger.info(
                "devices_marked_offline_stale",
                house_id=hid,
                device_ids=device_ids,
                cutoff=cutoff.isoformat(),
            )
            await _aggregate_house_status(hid, session=session, touch_last_seen=False)

        if own_session and rows:
            await session.commit()
        return len(rows)
    finally:
        if own_session:
            await session.close()


async def _aggregate_house_status(
    house_id: str, *, session: AsyncSession, touch_last_seen: bool = True
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
        if touch_last_seen:
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
