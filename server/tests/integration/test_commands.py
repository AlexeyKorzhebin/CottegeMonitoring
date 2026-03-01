"""Integration tests for command lifecycle: send, ack, timeout, late ack, idempotent ack."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.command import Command
from cottage_monitoring.services.command_service import (
    handle_ack,
    retry_pending_commands,
    send_command,
)
from cottage_monitoring.services.house_service import ensure_house

pytestmark = pytest.mark.integration


async def test_send_command_creates_record(db_session: AsyncSession) -> None:
    """send_command creates a Command record with status='sent'."""
    house_id = "house-cmd-send"
    payload = {"ga": "1/1/1", "value": True}
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    cmd = await send_command(house_id, payload, session=db_session)
    await db_session.commit()

    assert cmd.request_id is not None
    assert cmd.house_id == house_id
    assert cmd.status == "sent"
    assert cmd.payload.get("ga") == "1/1/1"
    assert cmd.payload.get("value") is True
    assert cmd.ts_sent is not None


async def test_ack_updates_status(db_session: AsyncSession) -> None:
    """handle_ack updates status to ok/error and sets ts_ack."""
    house_id = "house-cmd-ack"
    payload = {"ga": "1/1/1", "value": True}
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    cmd = await send_command(house_id, payload, session=db_session)
    await db_session.commit()
    request_id_str = str(cmd.request_id)

    await handle_ack(
        house_id,
        request_id_str,
        {"status": "ok", "results": [{"ga": "1/1/1", "applied": True}]},
        session=db_session,
    )
    await db_session.commit()

    result = await db_session.execute(select(Command).where(Command.request_id == cmd.request_id))
    updated = result.scalar_one()
    assert updated.status == "ok"
    assert updated.ts_ack is not None
    assert updated.results == [{"ga": "1/1/1", "applied": True}]


async def test_timeout_scenario(db_session: AsyncSession) -> None:
    """No ack: old ts_sent, retry_pending_commands marks as timeout."""
    house_id = "house-cmd-timeout"
    payload = {"ga": "1/1/1", "value": True}
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    cmd = await send_command(house_id, payload, session=db_session)
    await db_session.commit()

    # Simulate old ts_sent (past timeout)
    cmd.ts_sent = datetime.now(UTC) - timedelta(seconds=120)
    await db_session.commit()

    await retry_pending_commands(session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(Command).where(Command.request_id == cmd.request_id))
    updated = result.scalar_one()
    assert updated.status == "timeout"


async def test_late_ack_after_timeout(db_session: AsyncSession) -> None:
    """Set status to 'timeout' manually, then handle_ack → status updates to ok."""
    house_id = "house-cmd-late-ack"
    payload = {"ga": "1/1/1", "value": True}
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    cmd = await send_command(house_id, payload, session=db_session)
    await db_session.commit()

    cmd.status = "timeout"
    await db_session.commit()

    request_id_str = str(cmd.request_id)
    await handle_ack(house_id, request_id_str, {"status": "ok"}, session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(Command).where(Command.request_id == cmd.request_id))
    updated = result.scalar_one()
    assert updated.status == "ok"
    assert updated.ts_ack is not None


async def test_idempotent_ack(db_session: AsyncSession) -> None:
    """handle_ack twice for same request_id → should not error."""
    house_id = "house-cmd-idempotent"
    payload = {"ga": "1/1/1", "value": True}
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    cmd = await send_command(house_id, payload, session=db_session)
    await db_session.commit()
    request_id_str = str(cmd.request_id)

    await handle_ack(house_id, request_id_str, {"status": "ok"}, session=db_session)
    await handle_ack(house_id, request_id_str, {"status": "ok"}, session=db_session)
    await db_session.commit()

    result = await db_session.execute(select(Command).where(Command.request_id == cmd.request_id))
    updated = result.scalar_one()
    assert updated.status == "ok"
