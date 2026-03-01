"""State API: GET /houses/{house_id}/state, GET /houses/{house_id}/state/{ga}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import get_session
from cottage_monitoring.deps import redis_cache
from cottage_monitoring.models.object import Object
from cottage_monitoring.models.state import CurrentState
from cottage_monitoring.schemas.state import StateRead

router = APIRouter()


@router.get("/houses/{house_id}/state")
async def get_house_state(
    house_id: str,
    ga: str | None = Query(None, description="Comma-separated GA list"),
    tag: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Current state for all objects of a house. Reads from Redis, fallback DB."""
    ga_filter = [g.strip() for g in ga.split(",")] if ga else None

    # Try Redis first
    if redis_cache.is_connected:
        try:
            all_states = await redis_cache.get_all_states(house_id)
            if all_states:
                items = []
                for state_ga, data in all_states.items():
                    if ga_filter and state_ga not in ga_filter:
                        continue
                    items.append(
                        StateRead(
                            house_id=house_id,
                            ga=state_ga,
                            ts=data.get("ts", 0),
                            value=data.get("value"),
                            datatype=data.get("datatype", 0),
                            server_received_ts=data.get("server_received_ts", ""),
                        )
                    )
                return {"items": [i.model_dump() for i in items], "total": len(items)}
        except Exception:
            pass

    # Fallback to DB
    query = select(CurrentState).where(CurrentState.house_id == house_id)
    if ga_filter:
        query = query.where(CurrentState.ga.in_(ga_filter))

    result = await session.execute(query)
    rows = result.scalars().all()

    # Enrich with object info if tag filter
    if tag:
        obj_result = await session.execute(
            select(Object.ga).where(
                Object.house_id == house_id, Object.tags.contains(tag)
            )
        )
        tagged_gas = {r for r in obj_result.scalars().all()}
        rows = [r for r in rows if r.ga in tagged_gas]

    items = [
        StateRead(
            house_id=r.house_id,
            ga=r.ga,
            ts=r.ts,
            value=r.value,
            datatype=r.datatype,
            server_received_ts=r.server_received_ts,
        )
        for r in rows
    ]
    return {"items": [i.model_dump(mode="json") for i in items], "total": len(items)}


@router.get("/houses/{house_id}/state/{ga:path}")
async def get_state_by_ga(
    house_id: str,
    ga: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Current state for a single GA. GA in URL uses dashes: 1-1-1 → 1/1/1."""
    ga = ga.replace("-", "/")

    # Try Redis
    if redis_cache.is_connected:
        try:
            data = await redis_cache.get_state(house_id, ga)
            if data:
                return StateRead(
                    house_id=house_id,
                    ga=ga,
                    ts=data.get("ts", 0),
                    value=data.get("value"),
                    datatype=data.get("datatype", 0),
                    server_received_ts=data.get("server_received_ts", ""),
                ).model_dump(mode="json")
        except Exception:
            pass

    # Fallback to DB
    result = await session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id, CurrentState.ga == ga
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="State not found")

    return StateRead(
        house_id=row.house_id,
        ga=row.ga,
        ts=row.ts,
        value=row.value,
        datatype=row.datatype,
        server_received_ts=row.server_received_ts,
    ).model_dump(mode="json")
