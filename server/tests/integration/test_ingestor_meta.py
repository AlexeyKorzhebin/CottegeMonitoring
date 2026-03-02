"""Integration tests for meta/objects ingestion: MQTT meta → schema_versions + objects."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.object import Object
from cottage_monitoring.models.schema_version import SchemaVersion
from cottage_monitoring.services.house_service import ensure_house
from cottage_monitoring.services.schema_service import handle_chunk_meta, handle_full_meta

pytestmark = pytest.mark.integration

FULL_META_PAYLOAD = {
    "ts": 1730000000,
    "schema_hash": "sha256:abc123",
    "count": 2,
    "objects": [
        {
            "id": 1,
            "address": "1/1/1",
            "name": "Свет",
            "datatype": 1001,
            "units": "",
            "tags": "control, light",
            "comment": "",
        },
        {
            "id": 2,
            "address": "1/3/1",
            "name": "Темп",
            "datatype": 9001,
            "units": "°C",
            "tags": "heat, temp",
            "comment": "",
        },
    ],
}

CHUNK_1_PAYLOAD = {
    "ts": 1730000000,
    "schema_hash": "sha256:def456",
    "count": 2,
    "chunk_no": 1,
    "chunk_total": 2,
    "objects": [
        {
            "id": 1,
            "address": "1/1/1",
            "name": "Свет",
            "datatype": 1001,
            "units": "",
            "tags": "control",
            "comment": "",
        }
    ],
}

CHUNK_2_PAYLOAD = {
    "ts": 1730000000,
    "schema_hash": "sha256:def456",
    "count": 2,
    "chunk_no": 2,
    "chunk_total": 2,
    "objects": [
        {
            "id": 2,
            "address": "1/3/1",
            "name": "Темп",
            "datatype": 9001,
            "units": "°C",
            "tags": "heat, temp",
            "comment": "",
        }
    ],
}


async def test_full_meta_creates_schema_version(db_session: AsyncSession) -> None:
    """Full meta saves schema_version record."""
    house_id = "house-meta-schema"
    await ensure_house(house_id, session=db_session)
    await handle_full_meta(house_id, "lm-main", FULL_META_PAYLOAD, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(SchemaVersion).where(
            SchemaVersion.house_id == house_id,
            SchemaVersion.device_id == "lm-main",
            SchemaVersion.schema_hash == "sha256:abc123",
        )
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.count == 2


async def test_full_meta_creates_objects(db_session: AsyncSession) -> None:
    """Objects from meta are saved to objects table."""
    house_id = "house-meta-objs"
    await ensure_house(house_id, session=db_session)
    await handle_full_meta(house_id, "lm-main", FULL_META_PAYLOAD, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Object).where(
            Object.house_id == house_id,
            Object.device_id == "lm-main",
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 2

    gas = {r.ga for r in rows}
    assert "1/1/1" in gas
    assert "1/3/1" in gas


async def test_is_timeseries_classification(db_session: AsyncSession) -> None:
    """Objects with tags temp/meter etc. are is_timeseries=True; control without timeseries indicators are False."""
    house_id = "house-meta-timeseries"
    await ensure_house(house_id, session=db_session)
    await handle_full_meta(house_id, "lm-main", FULL_META_PAYLOAD, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(Object).where(
            Object.house_id == house_id,
            Object.device_id == "lm-main",
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 2

    ga_to_timeseries = {r.ga: r.is_timeseries for r in rows}
    assert ga_to_timeseries["1/1/1"] is False  # control, light - no timeseries tags
    assert ga_to_timeseries["1/3/1"] is True   # temp tag → is_timeseries


async def test_chunked_meta_assembly(db_session: AsyncSession) -> None:
    """Sending all chunks assembles full schema."""
    house_id = "house-meta-chunk"
    await ensure_house(house_id, session=db_session)

    await handle_chunk_meta(house_id, "lm-main", 1, CHUNK_1_PAYLOAD, session=db_session)
    await handle_chunk_meta(house_id, "lm-main", 2, CHUNK_2_PAYLOAD, session=db_session)
    await db_session.commit()

    result = await db_session.execute(
        select(SchemaVersion).where(
            SchemaVersion.house_id == house_id,
            SchemaVersion.device_id == "lm-main",
            SchemaVersion.schema_hash == "sha256:def456",
        )
    )
    sv = result.scalar_one_or_none()
    assert sv is not None

    result = await db_session.execute(
        select(Object).where(
            Object.house_id == house_id,
            Object.device_id == "lm-main",
        )
    )
    objs = result.scalars().all()
    assert len(objs) == 2
