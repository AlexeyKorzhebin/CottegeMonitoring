"""Integration tests for edge cases: invalid JSON, unknown topic, duplicate meta, unknown GA."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.schema_version import SchemaVersion
from cottage_monitoring.models.state import CurrentState
from cottage_monitoring.services.house_service import ensure_house
from cottage_monitoring.services.ingestor import handle_message
from cottage_monitoring.services.schema_service import handle_full_meta
from cottage_monitoring.services.state_service import handle_state

pytestmark = pytest.mark.integration


class FakeMessage:
    """Simple mock for aiomqtt.Message."""

    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


async def test_invalid_json_skipped() -> None:
    """Call handle_message with non-JSON payload → no error, message skipped."""
    msg = FakeMessage(topic="cm/house-01/lm-main/v1/events", payload=b"not valid json")
    await handle_message(msg)  # no exception


async def test_unknown_topic_skipped() -> None:
    """Call handle_message with unknown topic → no error, logged as warning."""
    msg = FakeMessage(topic="random/unknown/topic/path", payload=b'{"ts": 123}')
    await handle_message(msg)  # no exception


async def test_duplicate_meta_same_hash(db_session: AsyncSession) -> None:
    """handle_full_meta twice with same schema_hash → only one schema_version record."""
    house_id = "house-dup-meta"
    schema_hash = "sha256:same123"
    payload = {
        "ts": 1730000000,
        "schema_hash": schema_hash,
        "count": 1,
        "objects": [
            {
                "id": 1,
                "address": "1/1/1",
                "name": "Obj",
                "datatype": 1001,
                "units": "",
                "tags": "control",
                "comment": "",
            },
        ],
    }

    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_full_meta(house_id, "lm-main", payload, session=db_session)
    await db_session.commit()

    await handle_full_meta(house_id, "lm-main", payload, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(SchemaVersion).where(
            SchemaVersion.house_id == house_id,
            SchemaVersion.device_id == "lm-main",
            SchemaVersion.schema_hash == schema_hash,
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 1


async def test_message_for_unknown_ga(db_session: AsyncSession) -> None:
    """handle_state for GA not in objects table → state still saved (no validation against objects)."""
    house_id = "house-unknown-ga"
    ga = "9/9/9"
    payload = {"ts": 1730000000, "value": 42, "datatype": 14}

    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    await handle_state(house_id, "lm-main", ga, payload, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(CurrentState).where(
            CurrentState.house_id == house_id,
            CurrentState.ga == ga,
        )
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.value == 42
    assert row.datatype == 14
