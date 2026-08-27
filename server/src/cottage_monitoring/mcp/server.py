"""MCP face of the Ops catalog: one Streamable HTTP tool per registered Op."""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.context import get_current_api_key_context
from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import MCP_TOOL_DURATION
from cottage_monitoring.ops.dispatch import dispatch
from cottage_monitoring.ops.params import validate_params
from cottage_monitoring.ops.registry import all_ops
from cottage_monitoring.ops.spec import OpSpec
from cottage_monitoring.services.trace_service import record_trace

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


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _error_json(code: int, message: str) -> str:
    return _json({"status": "error", "code": code, "error": message})


async def _with_session(
    action: Callable[..., Awaitable[T]],
    *args: Any,
    tool: str = "unknown",
    house_id: str | None = None,
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
        MCP_TOOL_DURATION.labels(tool=tool).observe(time.perf_counter() - t0)
        logger.info("mcp_tool_error", tool=tool, code=exc.status_code, elapsed_ms=elapsed_ms)
        await record_trace(
            kind="mcp_tool",
            house_id=house_id,
            ref=tool,
            duration_ms=elapsed_ms,
            status="error",
            details={"code": exc.status_code, "error": detail},
        )
        return _error_json(exc.status_code, detail)
    elapsed = time.perf_counter() - t0
    MCP_TOOL_DURATION.labels(tool=tool).observe(elapsed)
    elapsed_ms = round(elapsed * 1000)
    logger.info("mcp_tool_done", tool=tool, elapsed_ms=elapsed_ms)
    status = data.get("status") if isinstance(data, dict) else None
    await record_trace(
        kind="mcp_tool",
        house_id=house_id,
        ref=tool,
        duration_ms=elapsed_ms,
        status=status or "ok",
        details={"result_status": status} if status else None,
    )
    return _json(data)


def _tool_signature(spec: OpSpec) -> inspect.Signature:
    """Signature FastMCP turns into the tool's JSON Schema.

    Op parameters come from the params model; house-scoped Ops additionally take
    an optional ``house_id``, which a single-house key may omit (design spec §9).
    """
    parameters = []
    if spec.params_model is not None:
        for name, field in spec.params_model.model_fields.items():
            parameters.append(
                inspect.Parameter(
                    name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=inspect.Parameter.empty if field.is_required() else field.default,
                    annotation=field.annotation,
                )
            )
    if spec.house_scoped:
        parameters.append(
            inspect.Parameter(
                "house_id",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=str | None,
            )
        )
    return inspect.Signature(parameters, return_annotation=str)


def _build_tool(spec: OpSpec) -> Callable[..., Awaitable[str]]:
    async def run_op(**arguments: Any) -> str:
        house_id = arguments.pop("house_id", None)
        ctx = get_current_api_key_context()

        async def call(session: AsyncSession) -> dict:
            params = validate_params(spec, arguments)
            return await dispatch(
                ctx, spec, house_id=house_id, params=params, session=session
            )

        traced_house = house_id or (ctx.default_house_id() if ctx else None)
        return await _with_session(call, tool=spec.name, house_id=traced_house)

    run_op.__name__ = spec.name
    run_op.__qualname__ = spec.name
    run_op.__doc__ = spec.description
    run_op.__signature__ = _tool_signature(spec)
    return run_op


_op_tools: dict[str, Callable[..., Awaitable[str]]] = {}


def register_op_tools() -> None:
    """Publish one MCP tool per registered Op. Idempotent; called by load_catalog()."""
    for spec in all_ops():
        if spec.name in _op_tools:
            continue
        tool = _build_tool(spec)
        _op_tools[spec.name] = tool
        mcp.add_tool(tool, name=spec.name, description=spec.description)


def create_mcp_app():
    return mcp.streamable_http_app()
