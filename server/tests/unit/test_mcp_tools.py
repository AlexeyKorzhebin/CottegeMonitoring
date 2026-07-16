"""MCP tool registration and auth gate tests (no live house/MQTT)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.auth.middleware import ApiKeyAuthMiddleware
from cottage_monitoring.mcp.server import mcp


def test_mcp_registers_expected_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "get_house_status",
        "discover",
        "get_temperature",
        "get_sensors",
        "list_lights",
        "set_light",
        "get_climate",
        "set_climate",
        "get_energy_status",
        "get_heating_diagnostics",
        "get_kettle",
        "set_kettle",
        "get_command_status",
    }
    assert expected <= names


def test_require_scope_denies_missing_write() -> None:
    from cottage_monitoring.mcp.server import _require_scope

    ctx = ApiKeyContext(
        key_id=uuid4(),
        house_id="house1",
        scopes=frozenset({"read"}),
        name="readonly",
    )
    err = _require_scope(ctx, "write")
    assert err is not None
    payload = json.loads(err)
    assert payload["status"] == "error"
    assert payload["code"] == 403
    assert "write" in payload["error"].lower()


def test_require_scope_allows_write() -> None:
    from cottage_monitoring.mcp.server import _require_scope

    ctx = ApiKeyContext(
        key_id=uuid4(),
        house_id="house1",
        scopes=frozenset({"read", "write"}),
        name="rw",
    )
    assert _require_scope(ctx, "write") is None


def test_with_session_maps_http_exception_to_json() -> None:
    from fastapi import HTTPException

    from cottage_monitoring.mcp.server import _with_session

    async def boom(_session):
        raise HTTPException(status_code=404, detail="No light found for: test")

    payload = json.loads(asyncio.run(_with_session(boom)))
    assert payload == {"status": "error", "code": 404, "error": "No light found for: test"}


def test_set_light_tool_returns_ambiguous_without_http_error() -> None:
    from cottage_monitoring.mcp import server as mcp_server

    ctx = ApiKeyContext(
        key_id=uuid4(),
        house_id="house1",
        scopes=frozenset({"read", "write"}),
        name="rw",
    )
    fake_session = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_session)
    cm.__aexit__ = AsyncMock(return_value=None)

    async def _run() -> str:
        with (
            patch.object(mcp_server, "get_current_api_key_context", return_value=ctx),
            patch.object(mcp_server.agent_actions, "check_write_rate_limit", AsyncMock()),
            patch.object(mcp_server, "async_session_factory", return_value=cm),
            patch.object(
                mcp_server.agent_actions,
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
            return await mcp_server.set_light(query="гостиная торшер", on=True)

    payload = json.loads(asyncio.run(_run()))
    assert payload["status"] == "ambiguous"
    assert len(payload["candidates"]) == 2


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

    ctx = ApiKeyContext(
        key_id=uuid4(),
        house_id="house1",
        scopes=frozenset({"read"}),
        name="readonly",
    )

    async def _run() -> str:
        with patch.object(mcp_server, "get_current_api_key_context", return_value=ctx):
            return await mcp_server.set_climate(query="кухня", setpoint_c=24.0)

    payload = json.loads(asyncio.run(_run()))
    assert payload["status"] == "error"
    assert payload["code"] == 403


def test_set_climate_tool_calls_service() -> None:
    from cottage_monitoring.mcp import server as mcp_server

    ctx = ApiKeyContext(
        key_id=uuid4(),
        house_id="house1",
        scopes=frozenset({"read", "write"}),
        name="rw",
    )
    fake_session = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_session)
    cm.__aexit__ = AsyncMock(return_value=None)

    async def _run() -> tuple[str, MagicMock]:
        set_sp = AsyncMock(
            return_value={"request_id": "r1", "ga": "1/6/7", "setpoint": 28}
        )
        with (
            patch.object(mcp_server, "get_current_api_key_context", return_value=ctx),
            patch.object(mcp_server.agent_actions, "check_write_rate_limit", AsyncMock()),
            patch.object(mcp_server, "async_session_factory", return_value=cm),
            patch.object(mcp_server.agent_actions, "set_climate_setpoint", set_sp),
        ):
            result = await mcp_server.set_climate(query="кухня", setpoint_c=28.0)
        return result, set_sp

    result, set_sp = asyncio.run(_run())
    payload = json.loads(result)
    assert payload["request_id"] == "r1"
    assert payload["ga"] == "1/6/7"
    set_sp.assert_awaited_once()
    assert set_sp.await_args.kwargs["setpoint_c"] == 28.0
    assert set_sp.await_args.kwargs["query"] == "кухня"
