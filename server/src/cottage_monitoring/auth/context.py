"""Request-scoped API key context."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ApiKeyContext:
    key_id: UUID
    house_id: str
    scopes: frozenset[str]
    name: str


api_key_context_var: ContextVar[ApiKeyContext | None] = ContextVar(
    "api_key_context", default=None
)

# When true, send_command resolves/persists but does not publish to MQTT.
command_dry_run_var: ContextVar[bool] = ContextVar("command_dry_run", default=False)


def get_current_api_key_context() -> ApiKeyContext | None:
    return api_key_context_var.get()


def is_command_dry_run() -> bool:
    return bool(command_dry_run_var.get())


def set_command_dry_run(enabled: bool) -> None:
    command_dry_run_var.set(bool(enabled))
