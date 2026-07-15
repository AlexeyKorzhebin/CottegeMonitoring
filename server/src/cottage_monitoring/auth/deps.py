"""FastAPI dependencies for API key auth."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.context import ApiKeyContext, api_key_context_var
from cottage_monitoring.auth.keys import verify_api_key
from cottage_monitoring.config import settings
from cottage_monitoring.db.session import get_session
from cottage_monitoring.models.api_key import ApiKey


def _extract_raw_key(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = request.headers.get("X-API-Key")
    if header:
        return header.strip()
    return None


async def authenticate_raw_key(
    raw_key: str,
    session: AsyncSession,
) -> ApiKeyContext:
    if not raw_key.startswith("cm_"):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    prefix = raw_key[:12]
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.key_prefix == prefix,
            ApiKey.revoked_at.is_(None),
        )
    )
    rows = result.scalars().all()
    matched: ApiKey | None = None
    for row in rows:
        if verify_api_key(raw_key, row.key_hash):
            matched = row
            break
    if matched is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    row = matched
    row.last_used_at = datetime.now(UTC)
    await session.commit()

    ctx = ApiKeyContext(
        key_id=row.id,
        house_id=row.house_id,
        scopes=frozenset(row.scopes or []),
        name=row.name,
    )
    api_key_context_var.set(ctx)
    return ctx


async def get_api_key_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiKeyContext | None:
    if not settings.auth_required:
        return None

    existing = getattr(request.state, "api_key_context", None)
    if existing is not None:
        return existing

    raw = _extract_raw_key(request)
    if not raw:
        raise HTTPException(status_code=401, detail="API key required")

    ctx = await authenticate_raw_key(raw, session)
    request.state.api_key_context = ctx
    return ctx


async def require_api_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiKeyContext:
    ctx = await get_api_key_context(request, session)
    if ctx is None:
        raise HTTPException(status_code=401, detail="API key required")
    return ctx


def require_scope(ctx: ApiKeyContext, scope: str) -> None:
    if scope not in ctx.scopes:
        raise HTTPException(
            status_code=403,
            detail=f"Scope '{scope}' required for this operation",
        )


def assert_house_access(ctx: ApiKeyContext, house_id: str) -> None:
    if ctx.house_id != house_id:
        raise HTTPException(status_code=403, detail="API key not valid for this house")
