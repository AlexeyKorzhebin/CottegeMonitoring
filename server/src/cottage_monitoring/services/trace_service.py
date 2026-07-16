"""Persist timing traces to PostgreSQL (enabled on dev by default)."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from cottage_monitoring.config import settings
from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.models.operation_trace import OperationTrace

logger = structlog.get_logger(__name__)


async def record_trace(
    *,
    kind: str,
    house_id: str | None = None,
    ref: str | None = None,
    duration_ms: int | None = None,
    status: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    if not settings.trace_persist:
        return
    try:
        async with async_session_factory() as session:
            session.add(
                OperationTrace(
                    id=uuid.uuid4(),
                    house_id=house_id,
                    kind=kind,
                    ref=ref,
                    duration_ms=duration_ms,
                    status=status,
                    details=details,
                )
            )
            await session.commit()
    except Exception:
        logger.warning("trace_persist_failed", kind=kind, ref=ref, exc_info=True)
