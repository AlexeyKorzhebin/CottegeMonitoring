"""House listing handler shared by REST GET /houses (and later MCP list_houses)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.device import Device
from cottage_monitoring.models.house import House
from cottage_monitoring.models.object import Object
from cottage_monitoring.models.schema_version import SchemaVersion
from cottage_monitoring.schemas.house import HouseRead


async def list_houses(
    session: AsyncSession,
    *,
    house_ids: frozenset[str] | None,
) -> dict:
    """List houses as HouseRead items. None = all houses; frozenset = grants only."""
    stmt = select(House)
    if house_ids is not None:
        stmt = stmt.where(House.house_id.in_(house_ids))
    result = await session.execute(stmt)
    houses = result.scalars().all()

    items = []
    for house in houses:
        obj_count_q = select(func.count()).select_from(Object).where(
            Object.house_id == house.house_id
        )
        object_count = (await session.execute(obj_count_q)).scalar_one()

        dev_count_q = select(func.count()).select_from(Device).where(
            Device.house_id == house.house_id
        )
        device_count = (await session.execute(dev_count_q)).scalar_one()

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
                device_count=device_count,
                current_schema_hash=current_schema_hash,
            )
        )

    return {"items": [i.model_dump(mode="json") for i in items], "total": len(items)}
