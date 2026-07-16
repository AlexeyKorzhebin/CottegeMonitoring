"""MCP Streamable HTTP server with semantic cottage tools."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from cottage_monitoring.auth.context import ApiKeyContext, get_current_api_key_context
from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import MCP_TOOL_DURATION
from cottage_monitoring.services import agent_actions

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# Mounted under FastAPI at /mcp → public URL ends at /mcp (path="/").
# DNS rebinding protection must allow nginx Host + loopback.
mcp = FastMCP(
    "CottageMonitoring",
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            "monitoring-dev.black-castle.ru",
            "monitoring.black-castle.ru",
        ],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            "https://monitoring-dev.black-castle.ru",
            "https://monitoring.black-castle.ru",
        ],
    ),
)


def _require_ctx() -> ApiKeyContext:
    ctx = get_current_api_key_context()
    if ctx is None:
        raise RuntimeError("API key required")
    return ctx


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _error_json(code: int, message: str) -> str:
    return _json({"status": "error", "code": code, "error": message})


def _require_scope(ctx: ApiKeyContext, scope: str) -> str | None:
    if scope not in ctx.scopes:
        return _error_json(403, f"Scope '{scope}' required")
    return None


async def _with_session(
    action: Callable[..., Awaitable[T]],
    *args: Any,
    tool: str = "unknown",
    **kwargs: Any,
) -> str:
    """Run a DB-backed action; map HTTPException to MCP JSON error contract."""
    t0 = time.perf_counter()
    try:
        async with async_session_factory() as session:
            data = await action(session, *args, **kwargs)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        MCP_TOOL_DURATION.labels(tool=tool).observe((time.perf_counter() - t0))
        logger.info("mcp_tool_error", tool=tool, code=exc.status_code, elapsed_ms=elapsed_ms)
        return _error_json(exc.status_code, detail)
    elapsed = time.perf_counter() - t0
    MCP_TOOL_DURATION.labels(tool=tool).observe(elapsed)
    elapsed_ms = round(elapsed * 1000)
    logger.info("mcp_tool_done", tool=tool, elapsed_ms=elapsed_ms)
    return _json(data)


@mcp.tool(description="Online status, last_seen, object counts for the authenticated house.")
async def get_house_status() -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(agent_actions.get_house_status, ctx.house_id, tool="get_house_status")


@mcp.tool(description="Find objects by name/query and kind: light, temp, climate, sensor, energy, heating, appliance, all.")
async def discover(query: str = "", kind: str = "all") -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(
        agent_actions.discover,
        ctx.house_id,
        query=query or None,
        kind=kind,
        tool="discover",
    )


@mcp.tool(
    description=(
        "Room air temperature (Zigbee 33/1/*), floor temperature (1/3/*), "
        "and outdoor weather. Prefer air sensors for room comfort."
    )
)
async def get_temperature(query: str = "") -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(
        agent_actions.get_temperatures,
        ctx.house_id,
        query=query or None,
        tool="get_temperature",
    )


@mcp.tool(description="Read sensors by kind or query: temp, humidity, meter, climate, etc.")
async def get_sensors(query: str = "", kind: str = "sensor") -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(
        agent_actions.get_sensors,
        ctx.house_id,
        query=query or None,
        kind=kind,
        tool="get_sensors",
    )


@mcp.tool(description="List lights with current on/off state.")
async def list_lights(query: str = "") -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(
        agent_actions.list_lights, ctx.house_id, query=query or None, tool="list_lights"
    )


@mcp.tool(description="Turn a light on or off by room/name query (single fixture).")
async def set_light(query: str, on: bool) -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "write"):
        return err
    await agent_actions.check_write_rate_limit(ctx)
    return await _with_session(
        agent_actions.set_light,
        ctx.house_id,
        query=query,
        on=on,
        tool="set_light",
    )


@mcp.tool(
    description=(
        "Turn multiple lights on/off in one MQTT batch. Use for zones: «1 этаж», «уличное», "
        "«2 этаж». Skips fixtures already in target state (skip_unchanged=true by default). "
        "Prefer over looping set_light — one request_id, one ack."
    )
)
async def set_lights(query: str, on: bool, skip_unchanged: bool = True) -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "write"):
        return err
    await agent_actions.check_write_rate_limit(ctx)
    return await _with_session(
        agent_actions.set_lights,
        ctx.house_id,
        query=query,
        on=on,
        skip_unchanged=skip_unchanged,
        tool="set_lights",
    )


@mcp.tool(
    description=(
        "Send arbitrary GA/value commands in batch. Input: items=[{ga,value}, ...]. "
        "Server groups items by device and sends minimal number of MQTT commands."
    )
)
async def set_commands(
    items: list[dict[str, Any]],
    comment: str = "",
    skip_unchanged: bool = True,
) -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "write"):
        return err
    await agent_actions.check_write_rate_limit(ctx)
    return await _with_session(
        agent_actions.set_commands,
        ctx.house_id,
        items=items,
        comment=comment or None,
        skip_unchanged=skip_unchanged,
        tool="set_commands",
    )


@mcp.tool(
    description=(
        "Underfloor heating: setpoints, floor/room temps, relay status, auto algorithm state. "
        "Setpoint alone does not enable heating — relays are managed by auto balancing (1/7/1)."
    )
)
async def get_climate(query: str = "") -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(
        agent_actions.get_climate, ctx.house_id, query=query or None, tool="get_climate"
    )


@mcp.tool(
    description=(
        "Set underfloor heating setpoint (°C) for a room. Does not force relay on. "
        "Use force_relay only for debug manual override."
    )
)
async def set_climate(
    query: str,
    setpoint_c: float,
    force_relay: bool | None = None,
) -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "write"):
        return err
    await agent_actions.check_write_rate_limit(ctx)
    return await _with_session(
        agent_actions.set_climate_setpoint,
        ctx.house_id,
        query=query,
        setpoint_c=setpoint_c,
        force_relay=force_relay,
        tool="set_climate",
    )


@mcp.tool(
    description=(
        "Electricity: total power, per-phase voltage/current/power, frequency, "
        "hourly/daily/total consumption."
    )
)
async def get_energy_status() -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(agent_actions.get_energy_status, ctx.house_id, tool="get_energy_status")


@mcp.tool(
    description=(
        "Warm floor diagnostics from 34/1/* (modes, blocks, weather k_base, power limit) "
        "and auto algorithm state 1/7/1."
    )
)
async def get_heating_diagnostics() -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(
        agent_actions.get_heating_diagnostics, ctx.house_id, tool="get_heating_diagnostics"
    )


@mcp.tool(
    description=(
        "Read BLE teapot status: on/state/temp as one appliance summary "
        "(cmd 33/1/39, state 33/1/38, temp 33/1/37)."
    )
)
async def get_kettle() -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(agent_actions.get_kettle, ctx.house_id, tool="get_kettle")


@mcp.tool(
    description=(
        "Control BLE teapot Redmond RK-M173S. Writes cmd GA 33/1/39 "
        "(tags: ble,control,zigbee_send). Prefer get_kettle before/after."
    )
)
async def set_kettle(on: bool) -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "write"):
        return err
    await agent_actions.check_write_rate_limit(ctx)
    return await _with_session(agent_actions.set_kettle, ctx.house_id, on=on, tool="set_kettle")


@mcp.tool(description="Poll command status by request_id after set_light/set_climate/set_kettle.")
async def get_command_status(request_id: str) -> str:
    ctx = _require_ctx()
    if err := _require_scope(ctx, "read"):
        return err
    return await _with_session(
        agent_actions.get_command_status, ctx.house_id, request_id, tool="get_command_status"
    )


def create_mcp_app():
    return mcp.streamable_http_app()
