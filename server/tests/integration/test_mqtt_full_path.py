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
    """Publish event to {prefix}cm/{house}/lm-main/v1/events → row appears in events table."""
    house_id = f"e2e-event-{uuid.uuid4().hex[:8]}"
    topic = f"{PREFIX}cm/{house_id}/lm-main/v1/events"
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
    """Publish state to {prefix}cm/{house}/lm-main/v1/state/ga/1/1/5 → current_state upserted."""
    house_id = f"e2e-state-{uuid.uuid4().hex[:8]}"
    ga = "1/1/5"
    topic = f"{PREFIX}cm/{house_id}/lm-main/v1/state/ga/{ga}"
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


# ---------- 2b. EVENT_BATCH ----------


async def test_events_batch_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish events/batch → multiple rows in events table."""
    house_id = f"e2e-batch-evt-{uuid.uuid4().hex[:8]}"
    topic = f"{PREFIX}cm/{house_id}/lm-main/v1/events/batch"
    payload = {
        "events": [
            {"ts": 1730001000, "seq": 1, "type": "knx.groupwrite", "ga": "1/1/1", "id": 1, "name": "A", "datatype": 1001, "value": True},
            {"ts": 1730001001, "seq": 2, "type": "knx.groupwrite", "ga": "1/1/2", "id": 2, "name": "B", "datatype": 1001, "value": False},
        ],
    }
    # Retry publish once on flaky MQTT (disconnect during iteration)
    for attempt in range(2):
        await asyncio.sleep(0.5 if attempt else 0)
        await _publish(topic, payload)

        async def _check():
            result = await db_session.execute(
                select(Event).where(Event.house_id == house_id).order_by(Event.seq)
            )
            rows = result.scalars().all()
            return rows if len(rows) >= 2 else None

        rows = await _poll(_check, timeout=8.0)
        if rows is not None:
            break
    assert rows is not None, "Events batch not found in DB (publish retried)"
    assert len(rows) >= 2
    assert rows[0].ga == "1/1/1" and rows[0].value is True
    assert rows[1].ga == "1/1/2" and rows[1].value is False


# ---------- 2c. STATE_BATCH ----------


async def test_states_batch_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish state/batch → multiple current_state rows upserted."""
    house_id = f"e2e-batch-st-{uuid.uuid4().hex[:8]}"
    topic = f"{PREFIX}cm/{house_id}/lm-main/v1/state/batch"
    payload = {
        "states": [
            {"ga": "1-1-10", "ts": 1730001100, "value": 100, "datatype": 7},
            {"ga": "1-1-11", "ts": 1730001100, "value": 200, "datatype": 7},
        ],
    }
    # Retry publish once on flaky MQTT (disconnect during iteration)
    rows_result = None
    for attempt in range(2):
        await asyncio.sleep(0.5 if attempt else 0)
        await _publish(topic, payload)

        async def _check():
            r1 = await db_session.execute(
                select(CurrentState).where(
                    CurrentState.house_id == house_id, CurrentState.ga == "1-1-10"
                )
            )
            r2 = await db_session.execute(
                select(CurrentState).where(
                    CurrentState.house_id == house_id, CurrentState.ga == "1-1-11"
                )
            )
            s1, s2 = r1.scalar_one_or_none(), r2.scalar_one_or_none()
            return (s1, s2) if s1 and s2 else None

        rows_result = await _poll(_check, timeout=8.0)
        if rows_result is not None:
            break
    assert rows_result is not None, "States batch not found in DB (publish retried)"
    row1, row2 = rows_result
    assert row1.value == 100
    assert row2.value == 200


# ---------- 3. META FULL ----------


async def test_meta_full_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Publish meta/objects → schema_versions + objects created."""
    house_id = f"e2e-meta-{uuid.uuid4().hex[:8]}"
    schema_hash = f"sha256:{uuid.uuid4().hex}"
    topic = f"{PREFIX}cm/{house_id}/lm-main/v1/meta/objects"
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

    topic1 = f"{PREFIX}cm/{house_id}/lm-main/v1/meta/objects/chunk/1"
    await _publish(topic1, {
        **base,
        "chunk_no": 1,
        "chunk_total": 2,
        "objects": [{"id": 200, "address": "2/1/1", "name": "Obj A", "datatype": 14, "units": "V", "tags": "meter", "comment": ""}],
    })

    topic2 = f"{PREFIX}cm/{house_id}/lm-main/v1/meta/objects/chunk/2"
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
    topic = f"{PREFIX}cm/{house_id}/lm-main/v1/status/online"
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


# ---------- 6. REST → MQTT (команда включить свет) ----------


async def test_client_receives_two_commands_tambur(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST двух команд (свет тамбур + теплый пол 25°C) → клиент получает обе в MQTT."""
    house_id = f"e2e-tambur-{uuid.uuid4().hex[:8]}"
    device_id = "lm-main"
    ga_light = "1/1/2"  # Свет - тамбур
    ga_floor_temp = "1/6/2"  # Темп теплого пола - тамбур

    await ensure_house(house_id, session=db_session)
    for obj in [
        Object(
            house_id=house_id,
            ga=ga_light,
            device_id=device_id,
            object_id=2401,
            name="Свет - тамбур",
            datatype=1001,
            tags="control,light,tambur",
            is_active=True,
        ),
        Object(
            house_id=house_id,
            ga=ga_floor_temp,
            device_id=device_id,
            object_id=2402,
            name="Темп теплого пола - тамбур",
            datatype=9001,
            tags="temp,floor,tambur",
            is_active=True,
        ),
    ]:
        db_session.add(obj)
    await db_session.commit()

    cmd_topic = f"{PREFIX}cm/{house_id}/{device_id}/v1/cmd"
    received: list[dict] = []

    async def _subscribe_and_collect() -> None:
        async with aiomqtt.Client(
            hostname=settings.mqtt_host,
            port=settings.mqtt_port,
            identifier=f"test-sub-{uuid.uuid4().hex[:8]}",
        ) as sub_client:
            await sub_client.subscribe(cmd_topic, qos=0)
            async for msg in sub_client.messages:
                payload = json.loads(msg.payload.decode()) if msg.payload else {}
                received.append(payload)
                if len(received) >= 2:
                    break

    sub_task = asyncio.create_task(_subscribe_and_collect())
    await asyncio.sleep(0.5)

    # 1. Включи свет в тамбуре
    resp1 = await mqtt_app_client.post(
        f"/api/v1/houses/{house_id}/commands",
        json={"ga": ga_light, "value": True, "comment": "Включи свет в тамбуре"},
    )
    assert resp1.status_code == 201

    # 2. Установи температуру теплого пола в тамбуре 25°C
    resp2 = await mqtt_app_client.post(
        f"/api/v1/houses/{house_id}/commands",
        json={"ga": ga_floor_temp, "value": 25.0, "comment": "Установи температуру теплого пола в тамбуре 25С"},
    )
    assert resp2.status_code == 201

    try:
        await asyncio.wait_for(sub_task, timeout=POLL_TIMEOUT)
    except asyncio.TimeoutError:
        sub_task.cancel()
        raise AssertionError(
            f"Expected 2 MQTT messages on {cmd_topic}, got {len(received)}. "
            "Check MQTT broker and app mqtt_client."
        ) from None

    assert len(received) == 2, f"Expected 2 commands, got {len(received)}"

    by_ga = {p.get("ga"): p for p in received}
    assert ga_light in by_ga, f"Light command not found in {list(by_ga.keys())}"
    assert ga_floor_temp in by_ga, f"Floor temp command not found in {list(by_ga.keys())}"

    assert by_ga[ga_light]["value"] is True
    assert by_ga[ga_floor_temp]["value"] == 25.0
    assert "request_id" in by_ga[ga_light]
    assert "request_id" in by_ga[ga_floor_temp]


async def test_rest_command_light_on_published_to_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /api/v1/houses/{id}/commands {"ga": "1/1/1", "value": true} → сообщение в MQTT."""
    house_id = f"e2e-rest-mqtt-{uuid.uuid4().hex[:8]}"
    device_id = "lm-main"
    ga = "1/1/1"

    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    obj = Object(
        house_id=house_id,
        ga=ga,
        device_id=device_id,
        object_id=2305,
        name="Свет - крыльцо",
        datatype=1001,
        tags="control,light",
        is_active=True,
    )
    db_session.add(obj)
    await db_session.commit()

    cmd_topic = f"{PREFIX}cm/{house_id}/{device_id}/v1/cmd"
    received: list[dict] = []

    async def _subscribe_and_collect() -> None:
        async with aiomqtt.Client(
            hostname=settings.mqtt_host,
            port=settings.mqtt_port,
            identifier=f"test-sub-{uuid.uuid4().hex[:8]}",
        ) as sub_client:
            await sub_client.subscribe(cmd_topic, qos=0)
            async for msg in sub_client.messages:
                payload = json.loads(msg.payload.decode()) if msg.payload else {}
                received.append(payload)
                if received:
                    break

    sub_task = asyncio.create_task(_subscribe_and_collect())
    await asyncio.sleep(0.5)

    # REST API: POST команды включить свет
    resp = await mqtt_app_client.post(
        f"/api/v1/houses/{house_id}/commands",
        json={"ga": ga, "value": True, "comment": "Включить свет"},
    )
    assert resp.status_code == 201

    try:
        await asyncio.wait_for(sub_task, timeout=POLL_TIMEOUT)
    except asyncio.TimeoutError:
        sub_task.cancel()
        raise AssertionError(
            f"MQTT message not received on {cmd_topic} after REST command. "
            "Check MQTT broker and app mqtt_client."
        ) from None

    assert len(received) == 1
    payload = received[0]
    assert payload.get("ga") == ga
    assert payload.get("value") is True
    assert "request_id" in payload


# ---------- 7. CMD ACK ----------


async def test_cmd_ack_via_mqtt(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Create command via send_command(), publish ack via MQTT → command.status = 'ok'."""
    house_id = f"e2e-ack-{uuid.uuid4().hex[:8]}"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    cmd = await send_command(house_id, "lm-main", {"ga": "1/1/1", "value": True}, session=db_session)
    await db_session.commit()
    request_id = str(cmd.request_id)

    topic = f"{PREFIX}cm/{house_id}/lm-main/v1/cmd/ack/{request_id}"
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

    topic = f"{PREFIX}cm/{house_id}/lm-main/v1/rpc/resp/{client_id}/{request_id}"
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
