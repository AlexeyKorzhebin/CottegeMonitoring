"""REST face of the Ops catalog (design spec §8): all Ops are POST, reads included."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.auth.deps import get_api_key_context
from cottage_monitoring.db.session import get_session
from cottage_monitoring.ops.dispatch import dispatch
from cottage_monitoring.ops.params import validate_params
from cottage_monitoring.ops.registry import all_ops, registry
from cottage_monitoring.ops.spec import OpSpec

router = APIRouter()


@router.get("/ops")
async def list_ops(
    ctx: ApiKeyContext | None = Depends(get_api_key_context),
) -> dict:
    """Catalog of Ops the caller's scopes allow. Auth off (dev) → everything."""
    items = [
        {
            "name": spec.name,
            "permission": spec.permission,
            "house_scoped": spec.house_scoped,
            "description": spec.description,
        }
        for spec in all_ops()
        if ctx is None or spec.permission in ctx.scopes
    ]
    return {"items": items, "total": len(items)}


def _house_scoped_op(name: str) -> OpSpec:
    """Only house-scoped Ops are callable here; list_houses lives at GET /houses."""
    spec = registry.get(name)
    if not spec.house_scoped:
        raise HTTPException(status_code=404, detail=f"Unknown op '{name}'")
    return spec


@router.post("/houses/{house_id}/ops/{name}")
async def call_op(
    house_id: str,
    name: str,
    body: dict[str, Any] | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
    ctx: ApiKeyContext | None = Depends(get_api_key_context),
) -> dict:
    """Run one Op against one house. Body carries the Op parameters, never house_id."""
    spec = _house_scoped_op(name)
    params = validate_params(spec, body)
    return await dispatch(ctx, spec, house_id=house_id, params=params, session=session)
