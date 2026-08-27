"""Ops registry and dispatcher (shared by the REST and MCP faces)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.ops import dispatch as dispatch_module
from cottage_monitoring.ops.dispatch import dispatch
from cottage_monitoring.ops.registry import OpsRegistry
from cottage_monitoring.ops.spec import OpSpec


def _ctx(*houses: str, scopes: tuple[str, ...] = ("read", "write")) -> ApiKeyContext:
    return ApiKeyContext(
        key_id=uuid4(),
        name="t",
        scopes=frozenset(scopes),
        house_ids=frozenset(houses),
    )


def _spec(
    handler: Any,
    *,
    name: str = "fake_op",
    permission: str = "read",
    house_scoped: bool = True,
) -> OpSpec:
    return OpSpec(
        name=name,
        permission=permission,
        house_scoped=house_scoped,
        description="fake op for tests",
        handler=handler,
        params_model=None,
    )


def _no_rate_limit() -> Any:
    return patch.object(
        dispatch_module.agent_actions, "check_write_rate_limit", AsyncMock()
    )


# --- registry ---------------------------------------------------------------


def test_registry_registers_and_looks_up_by_name() -> None:
    registry = OpsRegistry()
    spec = _spec(AsyncMock(), name="list_lights")
    registry.register(spec)
    assert registry.get("list_lights") is spec
    assert registry.names() == ("list_lights",)


def test_registry_names_are_sorted() -> None:
    registry = OpsRegistry()
    registry.register(_spec(AsyncMock(), name="set_light"))
    registry.register(_spec(AsyncMock(), name="get_kettle"))
    assert registry.names() == ("get_kettle", "set_light")


def test_registry_unknown_name_is_not_found() -> None:
    registry = OpsRegistry()
    with pytest.raises(HTTPException) as ei:
        registry.get("nope")
    assert ei.value.status_code == 404


def test_registry_rejects_duplicate_name() -> None:
    registry = OpsRegistry()
    registry.register(_spec(AsyncMock(), name="set_light"))
    with pytest.raises(ValueError):
        registry.register(_spec(AsyncMock(), name="set_light"))


# --- dispatch ---------------------------------------------------------------


def test_dispatch_calls_house_scoped_handler_with_house_and_params() -> None:
    handler = AsyncMock(return_value={"ok": True})
    session = MagicMock()
    result = asyncio.run(
        dispatch(
            _ctx("h1"),
            _spec(handler),
            house_id=None,
            params={"query": "кухня"},
            session=session,
        )
    )
    assert result == {"ok": True}
    handler.assert_awaited_once_with(session, "h1", query="кухня")


def test_dispatch_passes_house_ids_to_non_scoped_handler() -> None:
    handler = AsyncMock(return_value={"items": []})
    session = MagicMock()
    ctx = _ctx("h1", "h2")
    asyncio.run(
        dispatch(
            ctx,
            _spec(handler, name="list_houses", house_scoped=False),
            house_id="h1",
            params={},
            session=session,
        )
    )
    handler.assert_awaited_once_with(session, house_ids=ctx.house_ids)


def test_dispatch_denies_write_op_for_read_only_key() -> None:
    handler = AsyncMock()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            dispatch(
                _ctx("h1", scopes=("read",)),
                _spec(handler, name="set_light", permission="write"),
                house_id="h1",
                params={},
                session=MagicMock(),
            )
        )
    assert ei.value.status_code == 403
    handler.assert_not_awaited()


def test_dispatch_checks_write_rate_limit_for_write_op() -> None:
    handler = AsyncMock(return_value={"request_id": "r1"})
    ctx = _ctx("h1")
    with _no_rate_limit() as limiter:
        asyncio.run(
            dispatch(
                ctx,
                _spec(handler, name="set_light", permission="write"),
                house_id="h1",
                params={"on": True},
                session=MagicMock(),
            )
        )
    limiter.assert_awaited_once_with(ctx)
    handler.assert_awaited_once()


def test_dispatch_skips_write_rate_limit_for_read_op() -> None:
    handler = AsyncMock(return_value={})
    with _no_rate_limit() as limiter:
        asyncio.run(
            dispatch(
                _ctx("h1"),
                _spec(handler),
                house_id="h1",
                params={},
                session=MagicMock(),
            )
        )
    limiter.assert_not_awaited()


def test_dispatch_requires_house_id_for_two_grants() -> None:
    handler = AsyncMock()
    with _no_rate_limit() as limiter, pytest.raises(HTTPException) as ei:
        asyncio.run(
            dispatch(
                _ctx("h1", "h2"),
                _spec(handler, name="set_light", permission="write"),
                house_id=None,
                params={},
                session=MagicMock(),
            )
        )
    assert ei.value.status_code == 400
    assert ei.value.detail == "house_id required"
    handler.assert_not_awaited()
    limiter.assert_not_awaited()


def test_dispatch_denies_ungranted_house() -> None:
    handler = AsyncMock()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            dispatch(
                _ctx("h1"),
                _spec(handler),
                house_id="h2",
                params={},
                session=MagicMock(),
            )
        )
    assert ei.value.status_code == 403
    handler.assert_not_awaited()
