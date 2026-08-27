"""Op dispatcher shared by the REST and MCP faces (design spec §7)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.auth.deps import authorize, require_scope
from cottage_monitoring.ops.resolve_house import resolve_house_id
from cottage_monitoring.ops.spec import OpSpec
from cottage_monitoring.services import agent_actions


async def dispatch(
    ctx: ApiKeyContext,
    spec: OpSpec,
    *,
    house_id: str | None,
    params: dict,
    session: AsyncSession,
) -> dict:
    """Check permission, resolve the house, rate-limit writes, call the handler."""
    require_scope(ctx, spec.permission)

    resolved = resolve_house_id(ctx, spec.house_scoped, house_id)
    if resolved is not None:
        authorize(ctx, resolved, spec.permission)

    if spec.permission == "write":
        await agent_actions.check_write_rate_limit(ctx)

    if spec.house_scoped:
        return await spec.handler(session, resolved, **params)
    return await spec.handler(session, house_ids=ctx.house_ids, **params)
