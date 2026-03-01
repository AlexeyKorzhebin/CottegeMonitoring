"""Schema service: meta/objects handling, chunk assembly, object diff, is_timeseries classification."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.metrics import SCHEMA_CHANGES_TOTAL
from cottage_monitoring.models.object import Object
from cottage_monitoring.models.schema_version import SchemaVersion

logger = structlog.get_logger(__name__)

TIMESERIES_TAGS = {"temp", "meter", "humidity", "weather", "wind", "pressure_mm"}
TIMESERIES_UNITS = {"°C", "kWh", "kVARh", "W", "A", "V", "Hz", "%", "мм", "м/с", "VA", "VAR"}
NUMERIC_DATATYPES = {9, 9001, 14}

# In-memory chunk buffer: key = "{house_id}:{schema_hash}"
_chunk_buffer: dict[str, dict] = {}


def _should_be_timeseries(obj: dict) -> bool:
    tags = {t.strip() for t in obj.get("tags", "").split(",") if t.strip()}
    if tags & TIMESERIES_TAGS:
        return True
    if obj.get("datatype") in NUMERIC_DATATYPES and "control" not in tags:
        return True
    if obj.get("units", "") in TIMESERIES_UNITS:
        return True
    return False


async def handle_full_meta(
    house_id: str,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Handle full meta/objects message — save schema_version + upsert objects."""
    schema_hash = payload.get("schema_hash", "")
    objects_list = payload.get("objects", [])
    ts_epoch = payload.get("ts", 0)
    count = payload.get("count", len(objects_list))

    await _process_schema(house_id, schema_hash, ts_epoch, count, objects_list, payload, session=session)


async def handle_chunk_meta(
    house_id: str,
    chunk_no: int,
    payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Handle chunked meta/objects — buffer chunks and assemble when complete."""
    schema_hash = payload.get("schema_hash", "")
    chunk_total = payload.get("chunk_total", 1)
    buf_key = f"{house_id}:{schema_hash}"

    if buf_key not in _chunk_buffer:
        _chunk_buffer[buf_key] = {
            "schema_hash": schema_hash,
            "chunk_total": chunk_total,
            "ts": payload.get("ts", 0),
            "count": payload.get("count", 0),
            "received": {},
            "first_seen": datetime.now(UTC),
        }

    _chunk_buffer[buf_key]["received"][chunk_no] = payload.get("objects", [])

    if len(_chunk_buffer[buf_key]["received"]) >= chunk_total:
        all_objects = []
        for i in range(1, chunk_total + 1):
            all_objects.extend(_chunk_buffer[buf_key]["received"].get(i, []))

        buf = _chunk_buffer.pop(buf_key)
        full_payload = {
            "ts": buf["ts"],
            "schema_hash": schema_hash,
            "count": buf["count"],
            "objects": all_objects,
        }
        await _process_schema(
            house_id, schema_hash, buf["ts"], buf["count"], all_objects, full_payload, session=session
        )
        logger.info("chunk_assembly_complete", house_id=house_id, schema_hash=schema_hash, chunks=chunk_total)


async def _process_schema(
    house_id: str,
    schema_hash: str,
    ts_epoch: int,
    count: int,
    objects_list: list[dict],
    raw_payload: dict,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Save schema_version and upsert objects."""
    own_session = session is None
    if own_session:
        session = async_session_factory()

    try:
        ts = datetime.fromtimestamp(ts_epoch, tz=UTC)

        # Check if schema_version already exists
        result = await session.execute(
            select(SchemaVersion).where(
                SchemaVersion.house_id == house_id,
                SchemaVersion.schema_hash == schema_hash,
            )
        )
        existing_sv = result.scalar_one_or_none()

        if existing_sv is None:
            sv = SchemaVersion(
                house_id=house_id,
                schema_hash=schema_hash,
                ts=ts,
                count=count,
                raw_meta_json=raw_payload,
            )
            session.add(sv)
            SCHEMA_CHANGES_TOTAL.labels(house_id=house_id).inc()

        # Upsert objects
        new_gas = set()
        for obj_data in objects_list:
            ga = obj_data.get("address", "")
            new_gas.add(ga)

            result = await session.execute(
                select(Object).where(Object.house_id == house_id, Object.ga == ga)
            )
            existing_obj = result.scalar_one_or_none()

            is_ts = _should_be_timeseries(obj_data)

            if existing_obj:
                existing_obj.object_id = obj_data.get("id")
                existing_obj.name = obj_data.get("name", "")
                existing_obj.datatype = obj_data.get("datatype", 0)
                existing_obj.units = obj_data.get("units", "")
                existing_obj.tags = obj_data.get("tags", "")
                existing_obj.comment = obj_data.get("comment", "")
                existing_obj.schema_hash = schema_hash
                existing_obj.is_active = True
                existing_obj.is_timeseries = is_ts
                existing_obj.updated_at = datetime.now(UTC)
            else:
                new_obj = Object(
                    house_id=house_id,
                    ga=ga,
                    object_id=obj_data.get("id"),
                    name=obj_data.get("name", ""),
                    datatype=obj_data.get("datatype", 0),
                    units=obj_data.get("units", ""),
                    tags=obj_data.get("tags", ""),
                    comment=obj_data.get("comment", ""),
                    schema_hash=schema_hash,
                    is_active=True,
                    is_timeseries=is_ts,
                )
                session.add(new_obj)

        # Soft-delete objects not in the new schema
        result = await session.execute(
            select(Object).where(Object.house_id == house_id, Object.is_active.is_(True))
        )
        all_active = result.scalars().all()
        for obj in all_active:
            if obj.ga not in new_gas:
                obj.is_active = False
                obj.updated_at = datetime.now(UTC)

        if own_session:
            await session.commit()

        logger.info(
            "schema_processed",
            house_id=house_id,
            schema_hash=schema_hash,
            object_count=len(objects_list),
        )

    finally:
        if own_session:
            await session.close()
