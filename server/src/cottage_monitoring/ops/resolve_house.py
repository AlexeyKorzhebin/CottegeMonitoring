"""House resolve for Ops calls (design spec §9). Ambiguity is never guessed."""

from __future__ import annotations

from fastapi import HTTPException

from cottage_monitoring.auth.context import ApiKeyContext


def resolve_house_id(
    ctx: ApiKeyContext,
    house_scoped: bool,
    requested: str | None,
) -> str | None:
    """Return the house a house-scoped Op runs against, or None if not scoped.

    Membership only: scope/permission is checked by the dispatcher.
    """
    if not house_scoped:
        return None

    if not ctx.house_ids:
        raise HTTPException(status_code=403, detail="API key has no house grants")

    if requested is not None:
        if requested not in ctx.house_ids:
            raise HTTPException(
                status_code=403, detail="API key not valid for this house"
            )
        return requested

    default = ctx.default_house_id()
    if default is None:
        raise HTTPException(status_code=400, detail="house_id required")
    return default
