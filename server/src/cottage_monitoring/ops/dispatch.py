"""Op dispatcher shared by the REST and MCP faces (design spec §7)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.auth.deps import authorize, require_scope
from cottage_monitoring.config import settings
from cottage_monitoring.ops.resolve_house import resolve_house_id
from cottage_monitoring.ops.spec import OpSpec
from cottage_monitoring.services import agent_actions


async def dispatch(
    ctx: ApiKeyContext | None,
    spec: OpSpec,
    *,
    house_id: str | None,
    params: dict,
    session: AsyncSession,
) -> dict:
    """Check permission, resolve the house, rate-limit writes, call the handler."""
    if ctx is None:
        return await _dispatch_without_key(spec, house_id=house_id, params=params, session=session)

    require_scope(ctx, spec.permission)

    resolved = resolve_house_id(ctx, spec.house_scoped, house_id)
    if resolved is not None:
        authorize(ctx, resolved, spec.permission)

    if spec.permission == "write":
        await agent_actions.check_write_rate_limit(ctx)

    return await _call_handler(
        spec, session, house_id=resolved, house_ids=ctx.house_ids, params=params
    )


async def _dispatch_without_key(
    spec: OpSpec,
    *,
    house_id: str | None,
    params: dict,
    session: AsyncSession,
) -> dict:
    """No principal: 401, unless AUTH_REQUIRED=false opens everything (dev/test).

    That bypass is the same policy the resource REST already follows — with auth
    off, ``POST /commands`` and ``GET /houses`` serve any house without a key.
    There is no principal to scope or rate-limit against, so both are skipped.
    """
    if settings.auth_required:
        raise HTTPException(status_code=401, detail="API key required")

    if spec.house_scoped and house_id is None:
        raise HTTPException(status_code=400, detail="house_id required")

    return await _call_handler(spec, session, house_id=house_id, house_ids=None, params=params)


async def _call_handler(
    spec: OpSpec,
    session: AsyncSession,
    *,
    house_id: str | None,
    house_ids: frozenset[str] | None,
    params: dict,
) -> dict:
    if spec.house_scoped:
        return await spec.handler(session, house_id, **params)
    return await spec.handler(session, house_ids=house_ids, **params)
