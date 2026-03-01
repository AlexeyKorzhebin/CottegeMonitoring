"""RPC API: POST /houses/{house_id}/rpc/meta, POST /houses/{house_id}/rpc/snapshot."""

from __future__ import annotations

from fastapi import APIRouter

from cottage_monitoring.services.rpc_service import request_meta, request_snapshot

router = APIRouter()


@router.post("/houses/{house_id}/rpc/meta", status_code=202)
async def rpc_request_meta(house_id: str) -> dict:
    """Request meta via RPC. Returns 202 with request_id."""
    request_id = await request_meta(house_id)
    return {"request_id": request_id, "status": "requested"}


@router.post("/houses/{house_id}/rpc/snapshot", status_code=202)
async def rpc_request_snapshot(house_id: str) -> dict:
    """Request snapshot via RPC. Returns 202 with request_id."""
    request_id = await request_snapshot(house_id)
    return {"request_id": request_id, "status": "requested"}
