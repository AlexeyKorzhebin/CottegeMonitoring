"""Events API: GET /houses/{house_id}/events, GET /houses/{house_id}/events/timeseries."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import get_session
from cottage_monitoring.models.event import Event
from cottage_monitoring.models.object import Object
from cottage_monitoring.schemas.event import EventRead, TimeseriesPoint, TimeseriesResponse

router = APIRouter()

VALID_INTERVALS = {"1m", "5m", "15m", "1h", "6h", "1d"}
VALID_AGGREGATIONS = {"avg", "min", "max", "last", "sum", "count"}


@router.get("/houses/{house_id}/events")
async def get_events(
    house_id: str,
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    ga: str | None = Query(None),
    type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Paginated event history with filters."""
    query = select(Event).where(Event.house_id == house_id)

    if from_ts:
        query = query.where(Event.ts >= from_ts)
    if to_ts:
        query = query.where(Event.ts <= to_ts)
    if ga:
        query = query.where(Event.ga == ga)
    if type:
        query = query.where(Event.type == type)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()

    query = query.order_by(Event.ts.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    rows = result.scalars().all()

    items = [
        EventRead.model_validate(r).model_dump(mode="json")
        for r in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/houses/{house_id}/events/timeseries")
async def get_timeseries(
    house_id: str,
    ga: str = Query(...),
    from_ts: datetime = Query(..., alias="from"),
    to_ts: datetime = Query(..., alias="to"),
    interval: str = Query("1h"),
    agg: str = Query("avg"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Aggregated timeseries data for charts."""
    if interval not in VALID_INTERVALS:
        raise HTTPException(400, f"Invalid interval. Choose from: {VALID_INTERVALS}")
    if agg not in VALID_AGGREGATIONS:
        raise HTTPException(400, f"Invalid aggregation. Choose from: {VALID_AGGREGATIONS}")

    # Get object name
    obj_result = await session.execute(
        select(Object.name).where(Object.house_id == house_id, Object.ga == ga)
    )
    object_name = obj_result.scalar_one_or_none()

    agg_func = {
        "avg": "AVG((value::text)::numeric)",
        "min": "MIN((value::text)::numeric)",
        "max": "MAX((value::text)::numeric)",
        "sum": "SUM((value::text)::numeric)",
        "count": "COUNT(*)",
        "last": "LAST((value::text)::numeric, ts)",
    }[agg]

    sql = text(f"""
        SELECT time_bucket(:interval, ts) AS bucket, {agg_func} AS val
        FROM events
        WHERE house_id = :house_id AND ga = :ga AND ts >= :from_ts AND ts <= :to_ts
          AND value IS NOT NULL
        GROUP BY bucket
        ORDER BY bucket
    """)

    result = await session.execute(
        sql,
        {"interval": interval, "house_id": house_id, "ga": ga, "from_ts": from_ts, "to_ts": to_ts},
    )
    rows = result.all()

    points = [TimeseriesPoint(ts=r[0], value=float(r[1]) if r[1] is not None else None) for r in rows]

    return TimeseriesResponse(
        ga=ga,
        object_name=object_name,
        interval=interval,
        aggregation=agg,
        points=points,
    ).model_dump(mode="json")
