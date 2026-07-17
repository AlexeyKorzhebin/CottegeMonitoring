"""ASGI middleware: authenticate /api/v1 and /mcp when auth is required."""

from __future__ import annotations

import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from cottage_monitoring.auth.deps import _extract_raw_key, authenticate_raw_key
from cottage_monitoring.auth.context import set_command_dry_run
from cottage_monitoring.config import settings
from cottage_monitoring.db.session import async_session_factory

_HOUSE_PATH = re.compile(r"^/api/v1/houses/([^/]+)")
_DRY_RUN_TRUE = frozenset({"1", "true", "yes", "on"})


def _header_dry_run(request: Request) -> bool:
    raw = (request.headers.get("X-Cottage-Dry-Run") or "").strip().lower()
    return raw in _DRY_RUN_TRUE


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    _OPEN_PREFIXES = ("/health", "/metrics", "/docs", "/openapi.json", "/redoc")

    async def dispatch(self, request: Request, call_next) -> Response:
        # Always reset per-request; dry-run is opt-in via header only.
        set_command_dry_run(_header_dry_run(request))

        if not settings.auth_required:
            return await call_next(request)

        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in self._OPEN_PREFIXES):
            return await call_next(request)

        protected = path.startswith("/api/v1") or path.startswith("/mcp")
        if not protected:
            return await call_next(request)

        raw = _extract_raw_key(request)
        if not raw:
            return JSONResponse(status_code=401, content={"detail": "API key required"})

        async with async_session_factory() as session:
            try:
                from fastapi import HTTPException

                ctx = await authenticate_raw_key(raw, session)
            except HTTPException:
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

        request.state.api_key_context = ctx

        match = _HOUSE_PATH.match(path)
        if match and match.group(1) != ctx.house_id:
            return JSONResponse(
                status_code=403,
                content={"detail": "API key not valid for this house"},
            )

        return await call_next(request)
