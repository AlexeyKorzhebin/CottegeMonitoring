"""Houses API: GET /houses, GET /houses/{house_id}, PATCH /houses/{house_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import get_session
from cottage_monitoring.models.house import House
from cottage_monitoring.models.object import Object
from cottage_monitoring.models.schema_version import SchemaVersion
from cottage_monitoring.schemas.house import HouseDetail, HouseRead, HouseUpdate

router = APIRouter()


@router.get("/houses")
async def list_houses(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """List all houses with object_count and current_schema_hash."""
    result = await session.execute(select(House))
    houses = result.scalars().all()

    items = []
    for house in houses:
        # Count objects for this house
        obj_count_q = select(func.count()).select_from(Object).where(
            Object.house_id == house.house_id
        )
        object_count = (await session.execute(obj_count_q)).scalar_one()

        # Get latest schema_hash
        schema_q = (
            select(SchemaVersion.schema_hash)
            .where(SchemaVersion.house_id == house.house_id)
            .order_by(SchemaVersion.ts.desc())
            .limit(1)
        )
        schema_result = await session.execute(schema_q)
        current_schema_hash = schema_result.scalar_one_or_none()

        items.append(
            HouseRead(
                house_id=house.house_id,
                created_at=house.created_at,
                last_seen=house.last_seen,
                online_status=house.online_status,
                is_active=house.is_active,
                object_count=object_count,
                current_schema_hash=current_schema_hash,
            )
        )

    return {"items": [i.model_dump(mode="json") for i in items], "total": len(items)}


@router.get("/houses/{house_id}")
async def get_house(
    house_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """House detail with schema_versions_count."""
    result = await session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    if not house:
        raise HTTPException(status_code=404, detail="House not found")

    # Count objects (total and active)
    obj_total_q = select(func.count()).select_from(Object).where(
        Object.house_id == house_id
    )
    object_count = (await session.execute(obj_total_q)).scalar_one()

    obj_active_q = select(func.count()).select_from(Object).where(
        Object.house_id == house_id, Object.is_active.is_(True)
    )
    active_object_count = (await session.execute(obj_active_q)).scalar_one()

    # Get current_schema_hash
    schema_q = (
        select(SchemaVersion.schema_hash)
        .where(SchemaVersion.house_id == house_id)
        .order_by(SchemaVersion.ts.desc())
        .limit(1)
    )
    schema_result = await session.execute(schema_q)
    current_schema_hash = schema_result.scalar_one_or_none()

    # Count schema_versions
    sv_count_q = select(func.count()).select_from(SchemaVersion).where(
        SchemaVersion.house_id == house_id
    )
    schema_versions_count = (await session.execute(sv_count_q)).scalar_one()

    return HouseDetail(
        house_id=house.house_id,
        created_at=house.created_at,
        last_seen=house.last_seen,
        online_status=house.online_status,
        is_active=house.is_active,
        object_count=object_count,
        current_schema_hash=current_schema_hash,
        active_object_count=active_object_count,
        schema_versions_count=schema_versions_count,
    ).model_dump(mode="json")


@router.patch("/houses/{house_id}")
async def update_house(
    house_id: str,
    body: HouseUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update house (e.g. is_active)."""
    result = await session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    if not house:
        raise HTTPException(status_code=404, detail="House not found")

    if body.is_active is not None:
        house.is_active = body.is_active

    await session.commit()
    await session.refresh(house)

    # Recompute object_count and current_schema_hash for HouseRead
    obj_count_q = select(func.count()).select_from(Object).where(
        Object.house_id == house_id
    )
    object_count = (await session.execute(obj_count_q)).scalar_one()

    schema_q = (
        select(SchemaVersion.schema_hash)
        .where(SchemaVersion.house_id == house_id)
        .order_by(SchemaVersion.ts.desc())
        .limit(1)
    )
    schema_result = await session.execute(schema_q)
    current_schema_hash = schema_result.scalar_one_or_none()

    return HouseRead(
        house_id=house.house_id,
        created_at=house.created_at,
        last_seen=house.last_seen,
        online_status=house.online_status,
        is_active=house.is_active,
        object_count=object_count,
        current_schema_hash=current_schema_hash,
    ).model_dump(mode="json")
