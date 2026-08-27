"""MCP face: tools generated from the Ops registry, auth gate, JSON error contract."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.auth.middleware import ApiKeyAuthMiddleware
from cottage_monitoring.mcp.server import mcp
from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.registry import all_ops
from cottage_monitoring.services import agent_actions


def _ctx(*houses: str, scopes: tuple[str, ...] = ("read", "write")) -> ApiKeyContext:
    return ApiKeyContext(
        key_id=uuid4(),
        name="mcp-test",
        scopes=frozenset(scopes),
        house_ids=frozenset(houses),
    )


def _session_cm(session: Any) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def test_mcp_registers_exactly_the_registered_ops() -> None:
    load_catalog()
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {spec.name for spec in all_ops()}


def test_tool_runs_through_fastmcp_argument_validation() -> None:
    """The generated signature must survive FastMCP's own arg model, not just a direct call."""
    from cottage_monitoring.mcp import server as mcp_server

    load_catalog()
    session = MagicMock()
    handler = AsyncMock(return_value={"items": [], "total": 0})

    async def _run() -> Any:
        with (
            patch.object(mcp_server, "get_current_api_key_context", return_value=_ctx("house1")),
            patch.object(
                mcp_server, "async_session_factory", return_value=_session_cm(session)
            ),
            patch.object(agent_actions, "list_lights", handler),
        ):
            return await mcp.call_tool("list_lights", {"query": "кухня"})

    result = asyncio.run(_run())
    blocks = result[0] if isinstance(result, tuple) else result
    payload = json.loads(blocks[0].text)
    assert payload == {"items": [], "total": 0}
    handler.assert_awaited_once_with(session, "house1", query="кухня")


def test_with_session_maps_http_exception_to_json() -> None:
    from fastapi import HTTPException

    from cottage_monitoring.mcp.server import _with_session

    async def boom(_session):
        raise HTTPException(status_code=404, detail="No light found for: test")

    payload = json.loads(asyncio.run(_with_session(boom)))
    assert payload == {"status": "error", "code": 404, "error": "No light found for: test"}


def test_set_light_tool_returns_ambiguous_without_http_error() -> None:
    from cottage_monitoring.mcp import server as mcp_server

    load_catalog()
    session = MagicMock()

    async def _run() -> str:
        with (
            patch.object(mcp_server, "get_current_api_key_context", return_value=_ctx("house1")),
            patch.object(agent_actions, "check_write_rate_limit", AsyncMock()),
            patch.object(mcp_server, "async_session_factory", return_value=_session_cm(session)),
            patch.object(
                agent_actions,
                "set_light",
                AsyncMock(
                    return_value={
                        "status": "ambiguous",
                        "candidates": [
                            {"name": "Свет - гостиная", "ga": "1/1/3"},
                            {"name": "Свет - гостиная торшер", "ga": "1/1/8"},
                        ],
                    }
                ),
            ),
        ):
            return await mcp_server._op_tools["set_light"](query="гостиная торшер", on=True)

    payload = json.loads(asyncio.run(_run()))
    assert payload["status"] == "ambiguous"
    assert len(payload["candidates"]) == 2


def test_single_house_tool_works_without_house_id_argument() -> None:
    """Telegram regression: a one-house key never passes house_id."""
    from cottage_monitoring.mcp import server as mcp_server

    load_catalog()
    session = MagicMock()
    status = AsyncMock(return_value={"online_status": "online"})

    async def _run() -> str:
        with (
            patch.object(mcp_server, "get_current_api_key_context", return_value=_ctx("house1")),
            patch.object(mcp_server, "async_session_factory", return_value=_session_cm(session)),
            patch.object(agent_actions, "get_house_status", status),
        ):
            return await mcp_server._op_tools["get_house_status"]()

    payload = json.loads(asyncio.run(_run()))
    assert payload["online_status"] == "online"
    status.assert_awaited_once_with(session, "house1")


def test_two_house_key_without_house_id_is_a_json_error() -> None:
    from cottage_monitoring.mcp import server as mcp_server

    load_catalog()

    async def _run() -> str:
        with (
            patch.object(
                mcp_server, "get_current_api_key_context", return_value=_ctx("house1", "house2")
            ),
            patch.object(
                mcp_server, "async_session_factory", return_value=_session_cm(MagicMock())
            ),
        ):
            return await mcp_server._op_tools["get_house_status"]()

    payload = json.loads(asyncio.run(_run()))
    assert payload == {"status": "error", "code": 400, "error": "house_id required"}


def test_two_house_key_with_house_id_reaches_the_named_house() -> None:
    from cottage_monitoring.mcp import server as mcp_server

    load_catalog()
    session = MagicMock()
    status = AsyncMock(return_value={"online_status": "online"})

    async def _run() -> str:
        with (
            patch.object(
                mcp_server, "get_current_api_key_context", return_value=_ctx("house1", "house2")
            ),
            patch.object(mcp_server, "async_session_factory", return_value=_session_cm(session)),
            patch.object(agent_actions, "get_house_status", status),
        ):
            return await mcp_server._op_tools["get_house_status"](house_id="house2")

    json.loads(asyncio.run(_run()))
    status.assert_awaited_once_with(session, "house2")


def test_tool_without_api_key_returns_json_401(monkeypatch) -> None:
    from cottage_monitoring.mcp import server as mcp_server

    monkeypatch.setattr("cottage_monitoring.ops.dispatch.settings.auth_required", True)
    load_catalog()

    async def _run() -> str:
        with (
            patch.object(mcp_server, "get_current_api_key_context", return_value=None),
            patch.object(
                mcp_server, "async_session_factory", return_value=_session_cm(MagicMock())
            ),
        ):
            return await mcp_server._op_tools["get_house_status"]()

    payload = json.loads(asyncio.run(_run()))
    assert payload == {"status": "error", "code": 401, "error": "API key required"}


def test_auth_middleware_rejects_mcp_without_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "cottage_monitoring.auth.middleware.settings.auth_required",
        True,
    )

    async def ok(_request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp/", ok, methods=["POST"])])
    app.add_middleware(ApiKeyAuthMiddleware)

    async def _run() -> int:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/mcp/", json={})
        return resp.status_code, resp.json()

    status, body = asyncio.run(_run())
    assert status == 401
    assert "API key" in body["detail"]


def test_auth_middleware_allows_health_without_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "cottage_monitoring.auth.middleware.settings.auth_required",
        True,
    )

    async def ok(_request):
        return JSONResponse({"status": "healthy"})

    app = Starlette(routes=[Route("/health", ok, methods=["GET"])])
    app.add_middleware(ApiKeyAuthMiddleware)

    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health")

    resp = asyncio.run(_run())
    assert resp.status_code == 200


def test_set_climate_tool_requires_write_scope() -> None:
    from cottage_monitoring.mcp import server as mcp_server

    load_catalog()

    async def _run() -> str:
        with (
            patch.object(
                mcp_server,
                "get_current_api_key_context",
                return_value=_ctx("house1", scopes=("read",)),
            ),
            patch.object(
                mcp_server, "async_session_factory", return_value=_session_cm(MagicMock())
            ),
        ):
            return await mcp_server._op_tools["set_climate"](query="кухня", setpoint_c=24.0)

    payload = json.loads(asyncio.run(_run()))
    assert payload["status"] == "error"
    assert payload["code"] == 403


def test_set_climate_tool_calls_service() -> None:
    from cottage_monitoring.mcp import server as mcp_server

    load_catalog()
    session = MagicMock()
    set_sp = AsyncMock(return_value={"request_id": "r1", "ga": "1/6/7", "setpoint": 28})

    async def _run() -> str:
        with (
            patch.object(mcp_server, "get_current_api_key_context", return_value=_ctx("house1")),
            patch.object(agent_actions, "check_write_rate_limit", AsyncMock()),
            patch.object(mcp_server, "async_session_factory", return_value=_session_cm(session)),
            patch.object(agent_actions, "set_climate_setpoint", set_sp),
        ):
            return await mcp_server._op_tools["set_climate"](query="кухня", setpoint_c=28.0)

    payload = json.loads(asyncio.run(_run()))
    assert payload["request_id"] == "r1"
    assert payload["ga"] == "1/6/7"
    set_sp.assert_awaited_once()
    assert set_sp.await_args.kwargs["setpoint_c"] == 28.0
    assert set_sp.await_args.kwargs["query"] == "кухня"


def test_list_houses_tool_uses_key_grants() -> None:
    from cottage_monitoring.mcp import server as mcp_server
    from cottage_monitoring.ops import houses as houses_ops

    load_catalog()
    session = MagicMock()
    ctx = _ctx("house1", "house2")
    handler = AsyncMock(return_value={"items": [], "total": 0})

    async def _run() -> str:
        with (
            patch.object(mcp_server, "get_current_api_key_context", return_value=ctx),
            patch.object(mcp_server, "async_session_factory", return_value=_session_cm(session)),
            patch.object(houses_ops, "list_houses", handler),
        ):
            return await mcp_server._op_tools["list_houses"]()

    json.loads(asyncio.run(_run()))
    handler.assert_awaited_once_with(session, house_ids=ctx.house_ids)
