"""E2E tests: MQTT publish → broker → ingestor → DB for all 7 topic types.

Each test publishes a message via aiomqtt to the real MQTT broker,
the running ingestor (started via mqtt_app_client fixture with LifespanManager)
receives it, dispatches to the appropriate service, and we verify the result in DB.

Requires: MQTT broker on localhost (SSH tunnel), MQTT_TOPIC_PREFIX from .env.test."""

from __future__ import annotations

import asyncio
import json
import uuid

import aiomqtt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.config import settings
from cottage_monitoring.models.command import Command
from cottage_monitoring.models.event import Event
from cottage_monitoring.models.house import House
from cottage_monitoring.models.object import Object
from cottage_monitoring.models.schema_version import SchemaVersion
from cottage_monitoring.models.state import CurrentState
from cottage_monitoring.services.command_service import send_command
from cottage_monitoring.services.house_service import ensure_house
from cottage_monitoring.services.rpc_service import _pending_rpc

pytestmark = pytest.mark.integration

PREFIX = settings.mqtt_topic_prefix
POLL_INTERVAL = 0.3
POLL_TIMEOUT = 5.0


async def _publish(topic: str, payload: dict) -> None:
    async with aiomqtt.Client(
        hostname=settings.mqtt_host,
        port=settings.mqtt_port,
        identifier=f"test-e2e-{uuid.uuid4().hex[:8]}",
    ) as client:
        await client.publish(topic, json.dumps(payload), qos=0)


async def _poll(coro, timeout: float = POLL_TIMEOUT) -> object:
    """Poll an async callable until it returns truthy or timeout."""
    elapsed = 0.0
    result = None
    while elapsed < timeout:
        result = await coro()
        if result:
            return result
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    return result


# ---------- 1. EVENT ----------


async def test_event_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish event to {prefix}lm/{house}/v1/events → row appears in events table."""
    house_id = f"e2e-event-{uuid.uuid4().hex[:8]}"
    topic = f"{PREFIX}lm/{house_id}/v1/events"
    payload = {
        "ts": 1730000000,
        "seq": 1,
        "type": "knx.groupwrite",
        "ga": "1/1/1",
        "id": 2305,
        "name": "Test light",
        "datatype": 1001,
        "value": True,
    }
    await _publish(topic, payload)

    async def _check():
        result = await db_session.execute(
            select(Event).where(Event.house_id == house_id, Event.ga == "1/1/1")
        )
        return result.scalar_one_or_none()

    row = await _poll(_check)
    assert row is not None, "Event not found in DB after MQTT publish"
    assert row.value is True
    assert row.datatype == 1001


# ---------- 2. STATE ----------


async def test_state_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish state to {prefix}lm/{house}/v1/state/ga/1/1/5 → current_state upserted."""
    house_id = f"e2e-state-{uuid.uuid4().hex[:8]}"
    ga = "1/1/5"
    topic = f"{PREFIX}lm/{house_id}/v1/state/ga/{ga}"
    payload = {"ts": 1730000100, "value": 42.5, "datatype": 9001}
    await _publish(topic, payload)

    async def _check():
        result = await db_session.execute(
            select(CurrentState).where(
                CurrentState.house_id == house_id, CurrentState.ga == ga
            )
        )
        return result.scalar_one_or_none()

    row = await _poll(_check)
    assert row is not None, "CurrentState not found in DB after MQTT publish"
    assert row.value == 42.5
    assert row.datatype == 9001


# ---------- 3. META FULL ----------


async def test_meta_full_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish meta/objects → schema_versions + objects created."""
    house_id = f"e2e-meta-{uuid.uuid4().hex[:8]}"
    schema_hash = f"sha256:{uuid.uuid4().hex}"
    topic = f"{PREFIX}lm/{house_id}/v1/meta/objects"
    payload = {
        "ts": 1730000200,
        "schema_version": 1,
        "schema_hash": schema_hash,
        "count": 2,
        "objects": [
            {"id": 100, "address": "1/1/1", "name": "Light", "datatype": 1001, "units": "", "tags": "control, light", "comment": ""},
            {"id": 101, "address": "1/3/1", "name": "Temp", "datatype": 9001, "units": "°C", "tags": "temp, heat", "comment": ""},
        ],
    }
    await _publish(topic, payload)

    async def _check_sv():
        result = await db_session.execute(
            select(SchemaVersion).where(
                SchemaVersion.house_id == house_id,
                SchemaVersion.schema_hash == schema_hash,
            )
        )
        return result.scalar_one_or_none()

    sv = await _poll(_check_sv)
    assert sv is not None, "SchemaVersion not found after MQTT publish"
    assert sv.count == 2

    result = await db_session.execute(
        select(Object).where(Object.house_id == house_id).order_by(Object.ga)
    )
    objects = result.scalars().all()
    assert len(objects) == 2
    assert objects[0].ga == "1/1/1"
    assert objects[1].ga == "1/3/1"
    assert objects[1].is_timeseries is True


# ---------- 4. META CHUNK ----------


async def test_meta_chunk_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish 2 meta chunks → assembled schema_version + objects."""
    house_id = f"e2e-chunk-{uuid.uuid4().hex[:8]}"
    schema_hash = f"sha256:{uuid.uuid4().hex}"
    base = {
        "ts": 1730000300,
        "schema_version": 1,
        "schema_hash": schema_hash,
        "count": 2,
    }

    topic1 = f"{PREFIX}lm/{house_id}/v1/meta/objects/chunk/1"
    await _publish(topic1, {
        **base,
        "chunk_no": 1,
        "chunk_total": 2,
        "objects": [{"id": 200, "address": "2/1/1", "name": "Obj A", "datatype": 14, "units": "V", "tags": "meter", "comment": ""}],
    })

    topic2 = f"{PREFIX}lm/{house_id}/v1/meta/objects/chunk/2"
    await _publish(topic2, {
        **base,
        "chunk_no": 2,
        "chunk_total": 2,
        "objects": [{"id": 201, "address": "2/1/2", "name": "Obj B", "datatype": 14, "units": "A", "tags": "meter", "comment": ""}],
    })

    async def _check():
        result = await db_session.execute(
            select(SchemaVersion).where(
                SchemaVersion.house_id == house_id,
                SchemaVersion.schema_hash == schema_hash,
            )
        )
        return result.scalar_one_or_none()

    sv = await _poll(_check)
    assert sv is not None, "SchemaVersion not found after chunked MQTT publish"

    result = await db_session.execute(
        select(Object).where(Object.house_id == house_id).order_by(Object.ga)
    )
    objects = result.scalars().all()
    assert len(objects) == 2


# ---------- 5. STATUS ONLINE ----------


async def test_status_online_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish status/online → house.online_status = 'online'."""
    house_id = f"e2e-status-{uuid.uuid4().hex[:8]}"
    topic = f"{PREFIX}lm/{house_id}/v1/status/online"
    payload = {"ts": 1730000400, "status": "online", "version": "1.0.0"}
    await _publish(topic, payload)

    async def _check():
        result = await db_session.execute(
            select(House).where(House.house_id == house_id)
        )
        h = result.scalar_one_or_none()
        if h and h.online_status == "online":
            return h
        return None

    house = await _poll(_check)
    assert house is not None, "House not found or not online after MQTT publish"
    assert house.online_status == "online"


# ---------- 6. CMD ACK ----------


async def test_cmd_ack_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Create command via send_command(), publish ack via MQTT → command.status = 'ok'."""
    house_id = f"e2e-ack-{uuid.uuid4().hex[:8]}"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    cmd = await send_command(house_id, {"ga": "1/1/1", "value": True}, session=db_session)
    await db_session.commit()
    request_id = str(cmd.request_id)

    topic = f"{PREFIX}lm/{house_id}/v1/cmd/ack/{request_id}"
    ack_payload = {
        "ts": 1730000500,
        "request_id": request_id,
        "status": "ok",
        "results": [{"ga": "1/1/1", "applied": True}],
    }
    await _publish(topic, ack_payload)

    cmd_uuid = cmd.request_id

    async def _check():
        db_session.expire_all()
        result = await db_session.execute(
            select(Command).where(Command.request_id == cmd_uuid)
        )
        c = result.scalar_one_or_none()
        if c and c.status == "ok":
            return c
        return None

    updated = await _poll(_check)
    assert updated is not None, "Command status not updated to 'ok' after MQTT ack"
    assert updated.ts_ack is not None


# ---------- 7. RPC RESP ----------


async def test_rpc_resp_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Register pending RPC, publish rpc/resp via MQTT → request removed from _pending_rpc."""
    house_id = f"e2e-rpc-{uuid.uuid4().hex[:8]}"
    request_id = str(uuid.uuid4())
    client_id = settings.mqtt_client_id

    _pending_rpc[request_id] = {"method": "meta", "chunks": {}, "chunk_total": 1}

    topic = f"{PREFIX}lm/{house_id}/v1/rpc/resp/{client_id}/{request_id}"
    payload = {
        "request_id": request_id,
        "ok": True,
        "chunk_no": 1,
        "chunk_total": 1,
        "result": {"objects": []},
    }
    await _publish(topic, payload)

    async def _check():
        return request_id not in _pending_rpc

    removed = await _poll(_check)
    assert removed, f"RPC request {request_id} still in _pending_rpc after MQTT response"
