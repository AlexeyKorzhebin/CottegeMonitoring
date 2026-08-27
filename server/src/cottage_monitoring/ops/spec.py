"""One record per semantic operation — the single source of the Ops contract."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

Permission = Literal["read", "write"]


@dataclass(frozen=True)
class OpSpec:
    """Canonical Op description; both the REST and MCP faces are built from it.

    ``name`` is the MCP tool name and the URL segment at once. ``handler`` is
    awaited as ``(session, house_id, **params)`` for house-scoped Ops and as
    ``(session, **params)`` otherwise. ``params_model`` is None when the Op
    takes no parameters beyond session/house_id.
    """

    name: str
    permission: Permission
    house_scoped: bool
    description: str
    handler: Callable[..., Awaitable[dict]]
    params_model: type[BaseModel] | None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("OpSpec.name must be a non-empty string")
        if self.permission not in ("read", "write"):
            raise ValueError(
                f"OpSpec.permission must be 'read' or 'write', got {self.permission!r}"
            )
