"""Unit tests for command dry-run (no MQTT publish)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.command import Command
from cottage_monitoring.services.command_service import send_command
from cottage_monitoring.services.house_service import ensure_house

pytestmark = pytest.mark.integration


async def test_send_command_dry_run_skips_mqtt(db_session: AsyncSession) -> None:
    house_id = f"house-dry-{uuid4().hex[:8]}"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    with patch("cottage_monitoring.deps.mqtt_client") as mqtt:
        mqtt.publish = AsyncMock()
        cmd = await send_command(
            house_id,
            "lm-main",
            {"ga": "1/1/1", "value": True},
            session=db_session,
            dry_run=True,
        )
        await db_session.commit()

    assert cmd.status == "dry_run"
    assert cmd.payload.get("dry_run") is True
    assert cmd.payload.get("ga") == "1/1/1"
    mqtt.publish.assert_not_called()


async def test_send_command_dry_run_via_contextvar(db_session: AsyncSession) -> None:
    from cottage_monitoring.auth.context import set_command_dry_run

    house_id = f"house-dry-ctx-{uuid4().hex[:8]}"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    set_command_dry_run(True)
    try:
        with patch("cottage_monitoring.deps.mqtt_client") as mqtt:
            mqtt.publish = AsyncMock()
            cmd = await send_command(
                house_id,
                "lm-main",
                {"items": [{"ga": "1/1/1", "value": False}]},
                session=db_session,
            )
            await db_session.commit()
        assert cmd.status == "dry_run"
        mqtt.publish.assert_not_called()
    finally:
        set_command_dry_run(False)
