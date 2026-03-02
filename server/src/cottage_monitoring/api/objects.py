"""Objects API: GET /houses/{house_id}/objects, GET /houses/{house_id}/objects/{ga}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import get_session
from cottage_monitoring.models.object import Object
from cottage_monitoring.schemas.object import ObjectRead

router = APIRouter()


@router.get("/houses/{house_id}/objects")
async def get_objects(
    house_id: str,
    tag: str | None = Query(None),
    q: str | None = Query(None),
    is_active: bool | None = Query(None),
    is_timeseries: bool | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """List objects for a house with filters."""
    query = select(Object).where(Object.house_id == house_id)

    if tag:
        query = query.where(Object.tags.contains(tag))
    if q:
        query = query.where(Object.name.icontains(q))
    if is_active is not None:
        query = query.where(Object.is_active == is_active)
    if is_timeseries is not None:
        query = query.where(Object.is_timeseries == is_timeseries)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()

    query = query.order_by(Object.ga).limit(limit).offset(offset)
    result = await session.execute(query)
    rows = result.scalars().all()

    items = [ObjectRead.model_validate(r).model_dump(mode="json") for r in rows]
    return {"items": items, "total": total}


@router.get("/houses/{house_id}/objects/{ga:path}")
async def get_object(
    house_id: str,
    ga: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get single object details. GA in URL uses dashes: 1-1-1 → 1/1/1."""
    ga = ga.replace("-", "/")

    result = await session.execute(
        select(Object).where(Object.house_id == house_id, Object.ga == ga)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")

    return ObjectRead.model_validate(obj).model_dump(mode="json")
