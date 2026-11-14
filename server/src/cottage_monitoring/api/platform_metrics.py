"""Bounded, independently authenticated platform aggregate receiver."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.responses import JSONResponse

from cottage_monitoring.config import settings

router = APIRouter()
_LIMIT = 65536
_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$")
_READY = [
    "gateway",
    "qwen",
    "studio",
    "dispatcher",
    "comfy-studio",
    "ltx",
    "h3-native",
    "ops-read",
    "litellm",
    "admission",
    "open-webui",
    "caddy",
    "homepage",
    "litellm-postgres",
    "litellm-redis",
]
_ALLOWED = {(s, "ready"): ("bool", 0, 1) for s in _READY}
_ALLOWED.update(
    {
        ("gateway", m): ("count", 0, 1000000)
        for m in ("requests_total_window", "errors_total_window", "busy_total_window")
    }
)
_ALLOWED.update({("gateway", m): ("count", 0, 100000) for m in ("active", "capacity")})
_ALLOWED[("gateway", "latency_mean_ms")] = ("ms", 0, 3600000)
_ALLOWED.update({("admission", m): ("count", 0, 1000000) for m in (
    "requests_total_window", "errors_total_window", "busy_total_window"
)})
_ALLOWED[("admission", "active")] = ("count", 0, 100000)
_ALLOWED[("admission", "latency_mean_ms")] = ("ms", 0, 3600000)
_ALLOWED.update(
    {
        ("ai-host", m): ("percent", 0, 100)
        for m in ("cpu_mean", "memory_used", "disk_used", "gpu_utilization")
    }
)
_ALLOWED.update(
    {
        ("ai-host", "gpu_temperature"): ("celsius", -20, 150),
        ("ai-host", "gpu_memory_used"): ("MiB", 0, 1000000),
        ("ai-host", "gpu_power"): ("watt", 0, 10000),
        ("fan-controller", "pwm"): ("percent", 0, 100),
        ("collector", "dropped_batches_total"): ("count", 0, 1000000000),
        ("collector", "buffer_batches"): ("count", 0, 1440),
    }
)
_ALLOWED.update(
    {(s, "active"): ("bool", 0, 1) for s in ("gpu-thermal-guard", "fan-controller", "cooler-mqtt")}
)
_tokens, _last = 10.0, time.monotonic()
_engine = None
_engine_dsn = None


def _error(code: int, message: str, headers=None):
    return JSONResponse(status_code=code, content={"detail": message}, headers=headers)


def _timestamp(value):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError
    return datetime.fromisoformat(value[:-1] + "+00:00")


def validate(body: bytes, now: datetime):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    data = json.loads(
        body, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
    )
    if not isinstance(data, dict) or set(data) != {
        "version",
        "batch_id",
        "producer",
        "created_at",
        "samples",
    }:
        raise ValueError
    if type(data["version"]) is not int or data["version"] != 1 or data["producer"] != "ai-server":
        raise ValueError
    bid = data["batch_id"]
    if not isinstance(bid, str) or str(UUID(bid)) != bid or UUID(bid).version != 4:
        raise ValueError
    created = _timestamp(data["created_at"])
    if not now - timedelta(hours=24) <= created <= now + timedelta(minutes=5):
        raise ValueError
    samples = data["samples"]
    if not isinstance(samples, list) or not 1 <= len(samples) <= 128:
        raise ValueError
    seen = set()
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {
            "service",
            "metric",
            "unit",
            "observed_at",
            "status",
            "value",
        }:
            raise ValueError
        if not all(isinstance(sample[x], str) for x in ("service", "metric", "unit", "status")):
            raise ValueError
        key = (sample["service"], sample["metric"])
        if key in seen or key not in _ALLOWED:
            raise ValueError
        seen.add(key)
        unit, low, high = _ALLOWED[key]
        observed = _timestamp(sample["observed_at"])
        value, status = sample["value"], sample["status"]
        if sample["unit"] != unit or not created - timedelta(hours=24) <= observed <= created:
            raise ValueError
        if status == "unknown":
            if value is not None:
                raise ValueError
        elif status in ("observed", "estimated"):
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError
            if unit == "bool" and (type(value) is not int or value not in (0, 1)):
                raise ValueError
        else:
            raise ValueError
    return data


def _authorized(request: Request) -> bool:
    if not settings.platform_metrics_enabled or not settings.platform_metrics_token_file:
        return False
    try:
        token = Path(settings.platform_metrics_token_file).read_text(encoding="utf-8").strip()
        header = request.headers.get("authorization", "")
        return bool(token) and hmac.compare_digest(header.encode(), ("Bearer " + token).encode())
    except (OSError, UnicodeError):
        return False


def _rate_allowed():
    global _tokens, _last
    now = time.monotonic()
    _tokens = min(10.0, _tokens + max(0.0, now - _last))
    _last = now
    if _tokens < 1:
        return False
    _tokens -= 1
    return True


async def store(data, digest):
    global _engine, _engine_dsn
    dsn = settings.platform_metrics_db_url
    if not dsn or not dsn.startswith("postgresql+asyncpg://"):
        raise RuntimeError("store unavailable")
    if _engine is None:
        _engine = create_async_engine(
            dsn,
            pool_size=2,
            max_overflow=0,
            pool_timeout=2,
            connect_args={"timeout": 2, "command_timeout": 3},
            hide_parameters=True,
        )
        _engine_dsn = dsn
    if _engine_dsn != dsn:
        raise RuntimeError("store configuration changed")
    async with asyncio.timeout(5):
        async with _engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO platform_metrics.batches "
                        "(producer,batch_id,body_sha256,created_at) "
                        "VALUES (:producer,CAST(:batch_id AS uuid),:digest,:created_at) "
                        "ON CONFLICT DO NOTHING RETURNING batch_id"
                    ),
                    {
                        "producer": data["producer"],
                        "batch_id": data["batch_id"],
                        "digest": digest,
                        "created_at": _timestamp(data["created_at"]),
                    },
                )
            ).first()
            if row is None:
                old = (
                    await conn.execute(
                        text(
                            "SELECT body_sha256 FROM platform_metrics.batches "
                            "WHERE producer=:producer AND batch_id=CAST(:batch_id AS uuid)"
                        ),
                        {"producer": data["producer"], "batch_id": data["batch_id"]},
                    )
                ).scalar_one()
                return "duplicate" if hmac.compare_digest(bytes(old), digest) else "conflict"
            records = [
                {
                    **s,
                    "producer": data["producer"],
                    "batch_id": data["batch_id"],
                    "observed_at": _timestamp(s["observed_at"]),
                }
                for s in data["samples"]
            ]
            await conn.execute(
                text(
                    "INSERT INTO platform_metrics.samples "
                    "(producer,batch_id,service,metric,unit,observed_at,status,value) "
                    "VALUES (:producer,CAST(:batch_id AS uuid),:service,:metric,:unit,"
                    ":observed_at,:status,:value)"
                ),
                records,
            )
    return "accepted"


@router.post("/platform-metrics/batches")
async def ingest(request: Request):
    if not _authorized(request):
        return _error(401, "Unauthorized")
    if not _rate_allowed():
        return _error(429, "Rate limit exceeded", {"Retry-After": "1"})
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        return _error(400, "Invalid request")
    body = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(body) + len(chunk) > _LIMIT:
                    return _error(413, "Request too large")
                body.extend(chunk)
    except TimeoutError:
        return _error(400, "Invalid request")
    raw = bytes(body)
    try:
        data = validate(raw, datetime.now(UTC))
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
        return _error(400, "Invalid request")
    try:
        result = await store(data, hashlib.sha256(raw).digest())
    except Exception:
        return _error(503, "Service unavailable")
    if result == "conflict":
        return _error(409, "Batch conflict")
    return {"batch_id": data["batch_id"], "result": result}
