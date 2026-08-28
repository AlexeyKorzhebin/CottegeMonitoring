"""Drift guards: registry == MCP tools == GET /ops (design spec §15.1-15.3)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.registry import all_ops, op_names
from cottage_monitoring.services import agent_actions

# Design spec §12 — the one place the expected catalog is spelled out.
SPEC_CATALOG: dict[str, tuple[str, bool]] = {
    "list_houses": ("read", False),
    "get_house_status": ("read", True),
    "discover": ("read", True),
    "get_temperature": ("read", True),
    "get_sensors": ("read", True),
    "list_lights": ("read", True),
    "set_light": ("write", True),
    "set_lights": ("write", True),
    "set_commands": ("write", True),
    "get_climate": ("read", True),
    "set_climate": ("write", True),
    "set_auto_heating": ("write", True),
    "get_energy_status": ("read", True),
    "get_heating_diagnostics": ("read", True),
    "get_kettle": ("read", True),
    "set_kettle": ("write", True),
    "get_command_status": ("read", True),
}


def _ctx(*houses: str, scopes: tuple[str, ...] = ("read", "write")) -> ApiKeyContext:
    return ApiKeyContext(
        key_id=uuid4(),
        name="drift",
        scopes=frozenset(scopes),
        house_ids=frozenset(houses),
    )


def _session_cm(session: Any) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


# --- catalog ----------------------------------------------------------------


def test_catalog_matches_design_spec_table() -> None:
    load_catalog()
    actual = {spec.name: (spec.permission, spec.house_scoped) for spec in all_ops()}
    assert actual == SPEC_CATALOG


def test_load_catalog_is_idempotent() -> None:
    load_catalog()
    first = op_names()
    load_catalog()
    assert op_names() == first


def test_every_op_has_a_description() -> None:
    load_catalog()
    assert all(spec.description.strip() for spec in all_ops())


# --- MCP face ---------------------------------------------------------------


def test_mcp_tools_match_registry() -> None:
    load_catalog()
    names = {spec.name for spec in all_ops()}
    tool_names = {tool.name for tool in asyncio.run(mcp_list_tools())}
    assert names == tool_names


async def mcp_list_tools() -> list:
    from cottage_monitoring.mcp.server import mcp

    return await mcp.list_tools()


def test_house_scoped_tools_expose_optional_house_id() -> None:
    load_catalog()
    tools = {tool.name: tool for tool in asyncio.run(mcp_list_tools())}
    for name, (_, house_scoped) in SPEC_CATALOG.items():
        schema = tools[name].inputSchema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if house_scoped:
            assert "house_id" in properties, name
            assert "house_id" not in required, name
        else:
            assert "house_id" not in properties, name


def test_mcp_tool_schema_keeps_existing_arguments() -> None:
    load_catalog()
    tools = {tool.name: tool for tool in asyncio.run(mcp_list_tools())}
    assert set(tools["set_lights"].inputSchema["properties"]) == {
        "query",
        "on",
        "skip_unchanged",
        "house_id",
    }
    assert set(tools["set_lights"].inputSchema["required"]) == {"query", "on"}
    assert set(tools["get_energy_status"].inputSchema["properties"]) == {"house_id"}
    assert set(tools["set_auto_heating"].inputSchema["properties"]) == {"on", "house_id"}
    assert set(tools["set_auto_heating"].inputSchema["required"]) == {"on"}


# --- REST face --------------------------------------------------------------


def test_ops_catalog_lists_whole_registry_for_write_key() -> None:
    from cottage_monitoring.api.ops import list_ops

    load_catalog()
    payload = asyncio.run(list_ops(ctx=_ctx("house1")))
    assert {item["name"] for item in payload["items"]} == set(op_names())
    assert payload["total"] == len(op_names())
    first = payload["items"][0]
    assert set(first) == {"name", "permission", "house_scoped", "description"}


def test_ops_catalog_hides_write_ops_from_read_only_key() -> None:
    from cottage_monitoring.api.ops import list_ops

    load_catalog()
    payload = asyncio.run(list_ops(ctx=_ctx("house1", scopes=("read",))))
    names = {item["name"] for item in payload["items"]}
    write_names = {spec.name for spec in all_ops() if spec.permission == "write"}
    read_names = {spec.name for spec in all_ops() if spec.permission == "read"}
    assert write_names
    assert names == read_names


def test_ops_catalog_without_auth_lists_everything() -> None:
    from cottage_monitoring.api.ops import list_ops

    load_catalog()
    payload = asyncio.run(list_ops(ctx=None))
    assert {item["name"] for item in payload["items"]} == set(op_names())


# --- both faces, one handler ------------------------------------------------


def test_rest_and_mcp_reach_the_same_handler() -> None:
    from cottage_monitoring.api.ops import call_op
    from cottage_monitoring.mcp import server as mcp_server

    load_catalog()
    ctx = _ctx("house1")
    session = MagicMock()
    handler = AsyncMock(return_value={"items": [], "total": 0})

    async def _run() -> None:
        with (
            patch.object(agent_actions, "list_lights", handler),
            patch.object(mcp_server, "async_session_factory", return_value=_session_cm(session)),
            patch.object(mcp_server, "get_current_api_key_context", return_value=ctx),
        ):
            await mcp_server._op_tools["list_lights"]()
            await call_op(
                house_id="house1",
                name="list_lights",
                body=None,
                session=session,
                ctx=ctx,
            )

    asyncio.run(_run())

    assert handler.await_count == 2
    for call in handler.await_args_list:
        assert call.args == (session, "house1")
        assert call.kwargs == {"query": None}
