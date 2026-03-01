"""Integration tests for schema changes: objects add/remove, soft delete."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cottage_monitoring.models.object import Object
from cottage_monitoring.models.state import CurrentState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from cottage_monitoring.services.house_service import ensure_house
from cottage_monitoring.services.schema_service import handle_full_meta
from cottage_monitoring.services.state_service import handle_state

pytestmark = pytest.mark.integration

SCHEMA_V1 = {
    "ts": 1730000000,
    "schema_hash": "sha256:v1",
    "count": 2,
    "objects": [
        {
            "id": 1,
            "address": "1/1/1",
            "name": "Obj1",
            "datatype": 1001,
            "units": "",
            "tags": "control",
            "comment": "",
        },
        {
            "id": 2,
            "address": "1/3/1",
            "name": "Obj2",
            "datatype": 9001,
            "units": "°C",
            "tags": "temp",
            "comment": "",
        },
    ],
}


async def test_new_schema_adds_objects(db_session: AsyncSession) -> None:
    """New schema with objects → objects created."""
    house_id = "house-schema-add"
    await ensure_house(house_id, session=db_session)
    await handle_full_meta(house_id, SCHEMA_V1, session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(Object).where(Object.house_id == house_id))
    rows = result.scalars().all()
    assert len(rows) == 2
    gas = {r.ga for r in rows}
    assert "1/1/1" in gas
    assert "1/3/1" in gas


async def test_schema_removes_objects_soft_delete(db_session: AsyncSession) -> None:
    """New schema without an object → old object gets is_active=False (soft delete)."""
    house_id = "house-schema-soft-delete"
    await ensure_house(house_id, session=db_session)
    await handle_full_meta(house_id, SCHEMA_V1, session=db_session)
    await db_session.commit()

    schema_v2 = {
        "ts": 1730000100,
        "schema_hash": "sha256:v2",
        "count": 1,
        "objects": [
            {
                "id": 1,
                "address": "1/1/1",
                "name": "Obj1",
                "datatype": 1001,
                "units": "",
                "tags": "control",
                "comment": "",
            },
        ],
    }
    await handle_full_meta(house_id, schema_v2, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Object).where(Object.house_id == house_id, Object.ga == "1/3/1")
    )
    obj = result.scalar_one_or_none()
    assert obj is not None
    assert obj.is_active is False


async def test_empty_schema_deactivates_all(db_session: AsyncSession) -> None:
    """Schema with empty objects list → all objects is_active=False."""
    house_id = "house-schema-empty"
    await ensure_house(house_id, session=db_session)
    await handle_full_meta(house_id, SCHEMA_V1, session=db_session)
    await db_session.commit()

    schema_empty = {
        "ts": 1730000200,
        "schema_hash": "sha256:empty",
        "count": 0,
        "objects": [],
    }
    await handle_full_meta(house_id, schema_empty, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Object).where(Object.house_id == house_id, Object.is_active.is_(True))
    )
    active_rows = result.scalars().all()
    assert len(active_rows) == 0


async def test_state_for_inactive_objects_accepted(db_session: AsyncSession) -> None:
    """After soft delete, state can still be saved for inactive GA (no error)."""
    house_id = "house-schema-state-inactive"
    ga = "1/1/1"
    await ensure_house(house_id, session=db_session)
    await handle_full_meta(house_id, SCHEMA_V1, session=db_session)
    await db_session.commit()

    schema_v2 = {
        "ts": 1730000100,
        "schema_hash": "sha256:v2",
        "count": 0,
        "objects": [],
    }
    await handle_full_meta(house_id, schema_v2, session=db_session)
    await db_session.commit()

    await handle_state(
        house_id,
        ga,
        {"ts": 1730000200, "value": False, "datatype": 1001},
        session=db_session,
    )
    await db_session.commit()

    result = await db_session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id, CurrentState.ga == ga
        )
    )
    state = result.scalar_one_or_none()
    assert state is not None
    assert state.value is False
