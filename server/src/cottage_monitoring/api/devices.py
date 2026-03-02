"""Devices API: GET /houses/{house_id}/devices, GET/PATCH .../devices/{device_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import get_session
from cottage_monitoring.models.device import Device
from cottage_monitoring.schemas.device import DeviceRead, DeviceUpdate

router = APIRouter()


@router.get("/houses/{house_id}/devices")
async def list_devices(
    house_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Device).where(Device.house_id == house_id)
    )
    devices = result.scalars().all()
    items = [DeviceRead.model_validate(d).model_dump(mode="json") for d in devices]
    return {"items": items, "total": len(items)}


@router.get("/houses/{house_id}/devices/{device_id}")
async def get_device(
    house_id: str,
    device_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Device).where(Device.house_id == house_id, Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceRead.model_validate(device).model_dump(mode="json")


@router.patch("/houses/{house_id}/devices/{device_id}")
async def update_device(
    house_id: str,
    device_id: str,
    body: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Device).where(Device.house_id == house_id, Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    if body.is_active is not None:
        device.is_active = body.is_active

    await session.commit()
    await session.refresh(device)
    return DeviceRead.model_validate(device).model_dump(mode="json")
