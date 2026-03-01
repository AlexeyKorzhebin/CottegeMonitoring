"""Commands API: POST/GET /houses/{house_id}/commands, GET by request_id."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import get_session
from cottage_monitoring.models.command import Command
from cottage_monitoring.models.house import House
from cottage_monitoring.models.object import Object
from cottage_monitoring.schemas.command import CommandCreate, CommandRead
from cottage_monitoring.services.command_service import send_command

router = APIRouter()


def _build_items(body: CommandCreate) -> list[dict]:
    """Build items list from single (ga+value) or batch (items)."""
    if body.items:
        return [{"ga": item.ga, "value": item.value} for item in body.items]
    assert body.ga is not None and body.value is not None
    return [{"ga": body.ga, "value": body.value}]


@router.post("/houses/{house_id}/commands", status_code=201)
async def create_command(
    house_id: str,
    body: CommandCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send command. Validate house exists and is active, optionally validate GA."""
    result = await session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    if house is None:
        raise HTTPException(status_code=400, detail="House not found")
    if not house.is_active:
        raise HTTPException(status_code=400, detail="House is inactive")

    items = _build_items(body)
    for item in items:
        ga = item["ga"]
        obj_result = await session.execute(
            select(Object).where(Object.house_id == house_id, Object.ga == ga)
        )
        if obj_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail=f"Unknown GA: {ga}")

    payload: dict
    if len(items) == 1:
        payload = {"ga": items[0]["ga"], "value": items[0]["value"]}
    else:
        payload = {"items": items}
    if body.comment:
        payload["comment"] = body.comment

    cmd = await send_command(house_id, payload, session=session)
    await session.commit()

    return {
        "request_id": str(cmd.request_id),
        "house_id": cmd.house_id,
        "status": cmd.status,
        "ts_sent": cmd.ts_sent.isoformat(),
    }


@router.get("/houses/{house_id}/commands")
async def list_commands(
    house_id: str,
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Paginated list of commands with optional filters."""
    query = select(Command).where(Command.house_id == house_id)
    if from_ts:
        query = query.where(Command.ts_sent >= from_ts)
    if to_ts:
        query = query.where(Command.ts_sent <= to_ts)
    if status:
        query = query.where(Command.status == status)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()

    query = query.order_by(Command.ts_sent.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    rows = result.scalars().all()

    items = [CommandRead.model_validate(r).model_dump(mode="json") for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/houses/{house_id}/commands/{request_id}")
async def get_command(
    house_id: str,
    request_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get single command details. 404 if not found."""
    try:
        request_uuid = uuid.UUID(request_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail="Command not found") from err
    result = await session.execute(
        select(Command).where(
            Command.house_id == house_id,
            Command.request_id == request_uuid,
        )
    )
    cmd = result.scalar_one_or_none()
    if cmd is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return CommandRead.model_validate(cmd).model_dump(mode="json")
