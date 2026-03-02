"""Integration tests for multi-device houses: device auto-registration,
per-device meta, aggregated house status, command auto-resolve by GA."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cottage_monitoring.models.device import Device
from cottage_monitoring.models.house import House
from cottage_monitoring.models.object import Object
from cottage_monitoring.services.command_service import send_command
from cottage_monitoring.services.house_service import ensure_device, ensure_house, handle_status
from cottage_monitoring.services.schema_service import handle_full_meta
from cottage_monitoring.services.state_service import handle_state

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_multi_device_meta_no_conflict(db_session: AsyncSession) -> None:
    """Two devices in one house publish different meta — objects don't conflict."""
    house_id = "house-multi-meta"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    meta_1 = {
        "ts": 1730000000,
        "schema_hash": "sha256:aaa",
        "count": 2,
        "objects": [
            {"id": 1, "address": "1/1/1", "name": "Light Floor1", "datatype": 1001, "units": "", "tags": "", "comment": ""},
            {"id": 2, "address": "1/1/2", "name": "Light Floor1 Hall", "datatype": 1001, "units": "", "tags": "", "comment": ""},
        ],
    }
    await handle_full_meta(house_id, "lm-main", meta_1, session=db_session)
    await db_session.commit()

    meta_2 = {
        "ts": 1730000001,
        "schema_hash": "sha256:bbb",
        "count": 2,
        "objects": [
            {"id": 10, "address": "2/1/1", "name": "Light Floor2", "datatype": 1001, "units": "", "tags": "", "comment": ""},
            {"id": 11, "address": "2/1/2", "name": "Light Floor2 Hall", "datatype": 1001, "units": "", "tags": "", "comment": ""},
        ],
    }
    await handle_full_meta(house_id, "lm-floor2", meta_2, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Object).where(Object.house_id == house_id, Object.is_active.is_(True))
    )
    objects = result.scalars().all()
    assert len(objects) == 4

    device_ids = {o.device_id for o in objects}
    assert device_ids == {"lm-main", "lm-floor2"}


async def test_house_status_aggregation_all_online(db_session: AsyncSession) -> None:
    """All devices online → house status == 'online'."""
    house_id = "house-agg-online"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_status(house_id, "lm-main", {"ts": 1, "status": "online"}, session=db_session)
    await handle_status(house_id, "lm-floor2", {"ts": 2, "status": "online"}, session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one()
    assert house.online_status == "online"


async def test_house_status_aggregation_partial(db_session: AsyncSession) -> None:
    """One device online, one offline → house status == 'partial'."""
    house_id = "house-agg-partial"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_status(house_id, "lm-main", {"ts": 1, "status": "online"}, session=db_session)
    await handle_status(house_id, "lm-floor2", {"ts": 2, "status": "offline"}, session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one()
    assert house.online_status == "partial"


async def test_house_status_aggregation_all_offline(db_session: AsyncSession) -> None:
    """All devices offline → house status == 'offline'."""
    house_id = "house-agg-offline"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_status(house_id, "lm-main", {"ts": 1, "status": "offline"}, session=db_session)
    await handle_status(house_id, "lm-floor2", {"ts": 2, "status": "offline"}, session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one()
    assert house.online_status == "offline"


async def test_device_auto_registered(db_session: AsyncSession) -> None:
    """ensure_device auto-creates device record in DB."""
    house_id = "house-dev-auto"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await ensure_device(house_id, "lm-heating", session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Device).where(Device.house_id == house_id, Device.device_id == "lm-heating")
    )
    device = result.scalar_one_or_none()
    assert device is not None
    assert device.is_active is True
    assert device.online_status == "unknown"


async def test_state_records_device_id(db_session: AsyncSession) -> None:
    """handle_state saves device_id on current_state record."""
    house_id = "house-state-dev"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_state(
        house_id, "lm-main", "1/1/1",
        {"ts": 1730000000, "value": True, "datatype": 1001},
        session=db_session,
    )
    await db_session.commit()

    from cottage_monitoring.models.state import CurrentState
    result = await db_session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id, CurrentState.ga == "1/1/1"
        )
    )
    state = result.scalar_one()
    assert state.device_id == "lm-main"


async def test_command_auto_resolve_device_from_ga(db_session: AsyncSession) -> None:
    """send_command with device_id works; object.device_id used for resolution."""
    house_id = "house-cmd-resolve"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    meta = {
        "ts": 1730000000,
        "schema_hash": "sha256:ccc",
        "count": 1,
        "objects": [
            {"id": 1, "address": "1/1/1", "name": "Light", "datatype": 1001, "units": "", "tags": "", "comment": ""},
        ],
    }
    await handle_full_meta(house_id, "lm-main", meta, session=db_session)
    await db_session.commit()

    obj_result = await db_session.execute(
        select(Object).where(Object.house_id == house_id, Object.ga == "1/1/1")
    )
    obj = obj_result.scalar_one()
    assert obj.device_id == "lm-main"

    cmd = await send_command(house_id, "lm-main", {"ga": "1/1/1", "value": True}, session=db_session)
    await db_session.commit()
    assert cmd.device_id == "lm-main"


async def test_soft_delete_per_device(db_session: AsyncSession) -> None:
    """Meta from device A doesn't soft-delete objects from device B."""
    house_id = "house-soft-del"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    meta_a = {
        "ts": 1, "schema_hash": "sha256:a1", "count": 1,
        "objects": [{"id": 1, "address": "1/1/1", "name": "Obj A", "datatype": 1001, "units": "", "tags": "", "comment": ""}],
    }
    await handle_full_meta(house_id, "dev-a", meta_a, session=db_session)
    await db_session.commit()

    meta_b = {
        "ts": 2, "schema_hash": "sha256:b1", "count": 1,
        "objects": [{"id": 2, "address": "2/1/1", "name": "Obj B", "datatype": 1001, "units": "", "tags": "", "comment": ""}],
    }
    await handle_full_meta(house_id, "dev-b", meta_b, session=db_session)
    await db_session.commit()

    # Now dev-a publishes new meta without 1/1/1 → should soft-delete only dev-a's objects
    meta_a_v2 = {
        "ts": 3, "schema_hash": "sha256:a2", "count": 1,
        "objects": [{"id": 3, "address": "1/1/3", "name": "Obj A New", "datatype": 1001, "units": "", "tags": "", "comment": ""}],
    }
    await handle_full_meta(house_id, "dev-a", meta_a_v2, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Object).where(Object.house_id == house_id, Object.is_active.is_(True))
    )
    active = result.scalars().all()
    active_gas = {o.ga for o in active}
    assert "2/1/1" in active_gas, "dev-b's object must not be soft-deleted"
    assert "1/1/3" in active_gas, "dev-a's new object must be active"
    assert "1/1/1" not in active_gas, "dev-a's old object must be soft-deleted"
