"""Integration test: all objects from docs/objects.json via MQTT → DB verification.

1. Load objects.json, transform to meta/objects and state/ga format
2. Publish meta/objects (full) → schema_version + objects in DB
3. Publish state/ga/{ga} for each object with value → current_state in DB
4. Verify: objects count, current_state values match
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import aiomqtt
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.config import settings
from cottage_monitoring.models.object import Object
from cottage_monitoring.models.state import CurrentState

pytestmark = pytest.mark.integration

OBJECTS_JSON = Path(__file__).resolve().parents[3] / "docs" / "objects.json"

# Fallback sample when objects.json is missing/corrupted (from docs/objects.json structure)
OBJECTS_SAMPLE: list[dict] = [
    {"id": 2305, "address": "1/1/1", "name": "Light 1", "datatype": 1001, "tagcache": "control, light", "units": "", "comment": "", "value": False},
    {"id": 2818, "address": "1/3/2", "name": "Temp 1", "datatype": 9001, "tagcache": "heat, temp", "units": "°C", "comment": "", "value": 26.62},
    {"id": 65793, "address": "32/1/1", "name": "electric meter - Urms L1", "datatype": 14, "tagcache": "meter", "units": "V", "comment": "", "value": 232.38},
    {"id": 65803, "address": "32/1/11", "name": "electric meter - Irms L1", "datatype": 14, "tagcache": "meter", "units": "A", "comment": "", "value": 0.416},
    {"id": 65805, "address": "32/1/13", "name": "electric meter - P L1", "datatype": 14, "tagcache": "meter", "units": "W", "comment": "", "value": 38.5},
    {"id": 65827, "address": "32/1/35", "name": "electric meter - Total P", "datatype": 14, "tagcache": "meter", "units": "W", "comment": "", "value": 3410.0},
    {"id": 65809, "address": "32/1/17", "name": "electric meter - AP energy L1", "datatype": 14, "tagcache": "meter", "units": "kWh", "comment": "", "value": 20327.1},
    {"id": 65851, "address": "32/1/59", "name": "energy_meter - consumption Total", "datatype": 14, "tagcache": "meter", "units": "kWh", "comment": "", "value": 63907.8},
]
PREFIX = settings.mqtt_topic_prefix
POLL_INTERVAL = 0.2
POLL_TIMEOUT = 15.0


def _load_objects() -> list[dict]:
    if OBJECTS_JSON.exists():
        try:
            with open(OBJECTS_JSON, encoding="utf-8", errors="replace") as f:
                raw = json.load(f)
            out = [o for o in raw if o.get("address")]
            if out:
                return out
        except (json.JSONDecodeError, OSError):
            pass
    return OBJECTS_SAMPLE


def _to_meta_object(obj: dict) -> dict:
    return {
        "id": obj.get("id", 0),
        "address": obj["address"],
        "name": obj.get("name", ""),
        "datatype": obj.get("datatype", 0),
        "units": obj.get("units", ""),
        "tags": obj.get("tagcache", ""),
        "comment": obj.get("comment", ""),
    }


def _get_value(obj: dict) -> object:
    v = obj.get("value")
    if v is not None:
        return v
    return obj.get("data")


def _to_payload_str(payload: dict | str) -> str:
    return json.dumps(payload) if isinstance(payload, dict) else payload


async def _publish(client: aiomqtt.Client, topic: str, payload: dict | str, qos: int = 1) -> None:
    await client.publish(topic, _to_payload_str(payload), qos=qos)


async def _poll(coro, timeout: float = POLL_TIMEOUT) -> object:
    elapsed = 0.0
    result = None
    while elapsed < timeout:
        result = await coro()
        if result is not None:
            return result
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    return result


async def test_objects_json_full_ingest_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Send all objects from docs/objects.json via MQTT, verify meta + state in DB."""
    objects_raw = _load_objects()
    assert len(objects_raw) > 0, "objects.json is empty or has no address field"

    house_id = f"house-obj-ingest-{uuid.uuid4().hex[:12]}"
    schema_hash = f"sha256:{uuid.uuid4().hex}"
    ts = 1730000000

    # 1. Meta full + 2. State for each object with value — single MQTT connection
    meta_objects = [_to_meta_object(o) for o in objects_raw]
    meta_payload = {
        "ts": ts,
        "schema_version": 1,
        "schema_hash": schema_hash,
        "count": len(meta_objects),
        "objects": meta_objects,
    }
    meta_topic = f"{PREFIX}lm/{house_id}/v1/meta/objects"
    with_value = [(o, _get_value(o)) for o in objects_raw if _get_value(o) is not None and _get_value(o) != ""]

    async with aiomqtt.Client(
        hostname=settings.mqtt_host,
        port=settings.mqtt_port,
        identifier=f"test-obj-ingest-{uuid.uuid4().hex[:8]}",
    ) as mqtt_client:
        await _publish(mqtt_client, meta_topic, meta_payload)
        for obj, val in with_value:
            ga = obj["address"]
            state_topic = f"{PREFIX}lm/{house_id}/v1/state/ga/{ga}"
            state_payload = {"ts": ts, "value": val, "datatype": obj.get("datatype", 0)}
            await _publish(mqtt_client, state_topic, state_payload)

    async def _check_objects():
        result = await db_session.execute(
            select(func.count()).select_from(Object).where(Object.house_id == house_id)
        )
        n = result.scalar_one()
        if n >= len(objects_raw):
            return n
        return None

    obj_count = await _poll(_check_objects)
    assert obj_count == len(objects_raw), f"Expected {len(objects_raw)} objects, got {obj_count}"

    # 3. Verify current_state for objects with value
    async def _check_state_count():
        result = await db_session.execute(
            select(func.count()).select_from(CurrentState).where(CurrentState.house_id == house_id)
        )
        n = result.scalar_one()
        if n >= len(with_value):
            return n
        return None

    state_count = await _poll(_check_state_count)
    assert state_count == len(with_value), f"Expected {len(with_value)} state rows, got {state_count}"

    # 4. Spot-check values: compare stored vs expected
    result = await db_session.execute(
        select(CurrentState).where(CurrentState.house_id == house_id)
    )
    states = {s.ga: s for s in result.scalars().all()}
    expected_by_ga = {obj["address"]: _get_value(obj) for obj, _ in with_value}

    mismatches = []
    for ga, expected in list(expected_by_ga.items())[:20]:
        row = states.get(ga)
        if row is None:
            mismatches.append((ga, expected, None))
            continue
        stored = row.value
        if isinstance(expected, float) and isinstance(stored, (int, float)):
            if abs(float(stored) - expected) > 1e-6:
                mismatches.append((ga, expected, stored))
        elif stored != expected:
            mismatches.append((ga, expected, stored))

    assert not mismatches, f"Value mismatches: {mismatches[:5]}"
