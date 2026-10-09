"""Integration tests for online/offline status handling."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cottage_monitoring.config import settings
from cottage_monitoring.models.device import Device
from cottage_monitoring.models.house import House
from cottage_monitoring.services.ingestor import handle_message

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from cottage_monitoring.services.house_service import (
    ensure_house,
    handle_status,
    mark_stale_devices_offline,
)

pytestmark = pytest.mark.integration


async def test_status_online(db_session: AsyncSession) -> None:
    """handle_status with online → house.online_status == 'online'."""
    house_id = "house-status-online"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_status(
        house_id,
        "lm-main",
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
        "lm-main",
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
        "lm-main",
        {"ts": 1730000000, "status": "online"},
        session=db_session,
    )
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    assert house is not None
    assert house.is_active is True
    assert house.online_status == "online"


class _Msg:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


async def test_status_offline_topic_marks_house_offline(db_session: AsyncSession) -> None:
    """LWT topic status/offline is ingested, not dropped as an unknown topic."""
    house_id = "house-status-offline-topic"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()
    await handle_status(
        house_id,
        "lm-main",
        {"ts": 1730000000, "status": "online"},
        session=db_session,
    )
    await db_session.commit()

    payload = json.dumps({"ts": 1730000001, "status": "offline"}).encode()
    topic = f"{settings.mqtt_topic_prefix}cm/{house_id}/lm-main/v1/status/offline"
    await handle_message(_Msg(topic, payload))

    db_session.expire_all()
    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one()
    assert house.online_status == "offline"


async def test_stale_online_device_marked_offline(db_session: AsyncSession) -> None:
    """No messages for longer than the window → device and house go offline."""
    house_id = "house-stale-offline"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()
    await handle_status(
        house_id,
        "lm-main",
        {"ts": 1730000000, "status": "online"},
        session=db_session,
    )
    await db_session.commit()

    seen = datetime.now(UTC) - timedelta(minutes=10)
    device = (
        await db_session.execute(
            select(Device).where(Device.house_id == house_id, Device.device_id == "lm-main")
        )
    ).scalar_one()
    device.last_seen = seen
    house = (
        await db_session.execute(select(House).where(House.house_id == house_id))
    ).scalar_one()
    house.last_seen = seen
    await db_session.commit()

    changed = await mark_stale_devices_offline(session=db_session, house_id=house_id)
    await db_session.commit()
    assert changed == 1

    db_session.expire_all()
    device = (
        await db_session.execute(
            select(Device).where(Device.house_id == house_id, Device.device_id == "lm-main")
        )
    ).scalar_one()
    house = (
        await db_session.execute(select(House).where(House.house_id == house_id))
    ).scalar_one()
    assert device.online_status == "offline"
    assert house.online_status == "offline"
    assert house.last_seen is not None
    assert abs((house.last_seen - seen).total_seconds()) < 1


async def test_fresh_online_device_stays_online(db_session: AsyncSession) -> None:
    house_id = "house-stale-fresh"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()
    await handle_status(
        house_id,
        "lm-main",
        {"ts": 1730000000, "status": "online"},
        session=db_session,
    )
    await db_session.commit()

    changed = await mark_stale_devices_offline(session=db_session, house_id=house_id)
    await db_session.commit()
    assert changed == 0

    db_session.expire_all()
    house = (
        await db_session.execute(select(House).where(House.house_id == house_id))
    ).scalar_one()
    assert house.online_status == "online"


async def test_stale_sibling_leaves_fresh_device_online(db_session: AsyncSession) -> None:
    house_id = "house-stale-partial"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()
    await handle_status(house_id, "lm-main", {"ts": 1, "status": "online"}, session=db_session)
    await handle_status(house_id, "lm-floor2", {"ts": 2, "status": "online"}, session=db_session)
    await db_session.commit()

    stale = (
        await db_session.execute(
            select(Device).where(Device.house_id == house_id, Device.device_id == "lm-main")
        )
    ).scalar_one()
    stale.last_seen = datetime.now(UTC) - timedelta(minutes=10)
    await db_session.commit()

    changed = await mark_stale_devices_offline(session=db_session, house_id=house_id)
    await db_session.commit()
    assert changed == 1

    db_session.expire_all()
    devices = {
        d.device_id: d.online_status
        for d in (
            await db_session.execute(select(Device).where(Device.house_id == house_id))
        ).scalars()
    }
    house = (
        await db_session.execute(select(House).where(House.house_id == house_id))
    ).scalar_one()
    assert devices == {"lm-main": "offline", "lm-floor2": "online"}
    assert house.online_status == "partial"
