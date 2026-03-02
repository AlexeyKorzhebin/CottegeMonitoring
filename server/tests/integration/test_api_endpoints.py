"""Integration tests: полная проверка REST API по контракту api-v1.md.

Покрывает все endpoints: Houses, Devices, Objects, State, Events, Schemas,
Commands, RPC, Diagnostics. Использует подготовленные данные в БД.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.command import Command
from cottage_monitoring.models.object import Object
from cottage_monitoring.models.schema_version import SchemaVersion
from cottage_monitoring.models.state import CurrentState
from cottage_monitoring.services.house_service import ensure_house, ensure_device
from cottage_monitoring.services.event_service import handle_event

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_test_data(db_session: AsyncSession) -> dict:
    """Подготовка полного набора данных для тестирования API."""
    house_id = f"house-api-{uuid.uuid4().hex[:12]}"
    device_id = "lm-main"
    ga = "1/1/1"
    schema_hash = "sha256:test123"
    object_id_val = 2305

    await ensure_house(house_id, session=db_session)
    await ensure_device(house_id, device_id, session=db_session)
    await db_session.commit()

    obj = Object(
        house_id=house_id,
        ga=ga,
        device_id=device_id,
        object_id=object_id_val,
        name="Свет - крыльцо",
        datatype=1001,
        tags="control,light,outside",
        is_active=True,
        is_timeseries=True,
    )
    db_session.add(obj)

    sv = SchemaVersion(
        house_id=house_id,
        device_id=device_id,
        schema_hash=schema_hash,
        ts=datetime.now(UTC),
        count=1,
        raw_meta_json={
            "objects": [
                {"address": ga, "id": object_id_val, "name": "Свет - крыльцо", "datatype": 1001},
            ],
        },
    )
    db_session.add(sv)

    base_ts = int(datetime(2026, 2, 28, 10, 0, 0, tzinfo=UTC).timestamp())
    await handle_event(
        house_id,
        device_id,
        {"ts": base_ts, "seq": 1, "type": "knx.groupwrite", "ga": ga, "id": object_id_val, "name": "Свет - крыльцо", "datatype": 1001, "value": True},
        session=db_session,
    )

    state = CurrentState(
        house_id=house_id,
        ga=ga,
        ts=datetime.fromtimestamp(base_ts, tz=UTC),
        value=True,
        datatype=1001,
        server_received_ts=datetime.now(UTC),
    )
    db_session.add(state)

    cmd = Command(
        house_id=house_id,
        device_id=device_id,
        ts_sent=datetime.now(UTC),
        payload={"ga": ga, "value": True},
        status="ok",
    )
    db_session.add(cmd)

    await db_session.commit()

    return {
        "house_id": house_id,
        "device_id": device_id,
        "ga": ga,
        "ga_dash": ga.replace("/", "-"),
        "schema_hash": schema_hash,
        "request_id": str(cmd.request_id),
    }


# --- Diagnostics ---


async def test_health(async_client: AsyncClient) -> None:
    """GET /health → 200, status, mqtt_connected, db_connected, redis_connected, uptime_seconds."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "mqtt_connected" in data
    assert "db_connected" in data
    assert "redis_connected" in data
    assert "uptime_seconds" in data


async def test_metrics(async_client: AsyncClient) -> None:
    """GET /metrics → 200, text/plain."""
    resp = await async_client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")


# --- Houses ---


async def test_houses_list(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses → 200, items, total."""
    resp = await async_client.get("/api/v1/houses")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


async def test_house_detail(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id} → 200, house_id, object_count, schema_versions_count."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["house_id"] == house_id
    assert "object_count" in data
    assert "active_object_count" in data
    assert "schema_versions_count" in data


async def test_house_not_found(async_client: AsyncClient) -> None:
    """GET /api/v1/houses/nonexistent → 404."""
    resp = await async_client.get("/api/v1/houses/nonexistent")
    assert resp.status_code == 404


async def test_house_patch(async_client: AsyncClient, api_test_data: dict) -> None:
    """PATCH /api/v1/houses/{house_id} → 200, is_active обновлён."""
    house_id = api_test_data["house_id"]
    resp = await async_client.patch(f"/api/v1/houses/{house_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp2 = await async_client.patch(f"/api/v1/houses/{house_id}", json={"is_active": True})
    assert resp2.status_code == 200
    assert resp2.json()["is_active"] is True


# --- Devices ---


async def test_devices_list(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/devices → 200, items, total."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


async def test_device_detail(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/devices/{device_id} → 200."""
    house_id = api_test_data["house_id"]
    device_id = api_test_data["device_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["device_id"] == device_id


async def test_device_not_found(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/devices/nonexistent → 404."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/devices/nonexistent")
    assert resp.status_code == 404


async def test_device_patch(async_client: AsyncClient, api_test_data: dict) -> None:
    """PATCH /api/v1/houses/{house_id}/devices/{device_id} → 200."""
    house_id = api_test_data["house_id"]
    device_id = api_test_data["device_id"]
    resp = await async_client.patch(
        f"/api/v1/houses/{house_id}/devices/{device_id}",
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# --- Objects ---


async def test_objects_list(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/objects → 200, items, total."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/objects")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) >= 1


async def test_objects_list_with_filters(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/objects?tag=light&is_active=true → 200."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(
        f"/api/v1/houses/{house_id}/objects",
        params={"tag": "light", "is_active": "true", "is_timeseries": "true", "q": "крыльцо"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


async def test_object_detail(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/objects/{ga} (GA через дефис) → 200."""
    house_id = api_test_data["house_id"]
    ga_dash = api_test_data["ga_dash"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/objects/{ga_dash}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ga"] == api_test_data["ga"]
    assert "name" in data
    assert "tags" in data


async def test_object_not_found(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/objects/999-999-999 → 404."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/objects/999-999-999")
    assert resp.status_code == 404


# --- State ---


async def test_state_list(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/state → 200, items, total."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) >= 1


async def test_state_list_with_ga_filter(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/state?ga=1/1/1 → 200."""
    house_id = api_test_data["house_id"]
    ga = api_test_data["ga"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/state", params={"ga": ga})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


async def test_state_detail(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/state/{ga} → 200."""
    house_id = api_test_data["house_id"]
    ga_dash = api_test_data["ga_dash"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/state/{ga_dash}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ga"] == api_test_data["ga"]
    assert "value" in data


async def test_state_not_found(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/state/999-999-999 → 404."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/state/999-999-999")
    assert resp.status_code == 404


# --- Events ---


async def test_events_list(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/events?from=... → 200, items, total, limit, offset."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(
        f"/api/v1/houses/{house_id}/events",
        params={"from": "2026-02-28T00:00:00Z"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


async def test_events_list_with_filters(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/events?from=...&to=...&ga=...&type=...&limit=10&offset=0."""
    house_id = api_test_data["house_id"]
    ga = api_test_data["ga"]
    resp = await async_client.get(
        f"/api/v1/houses/{house_id}/events",
        params={
            "from": "2026-02-28T00:00:00Z",
            "to": "2026-03-01T00:00:00Z",
            "ga": ga,
            "type": "knx.groupwrite",
            "limit": 10,
            "offset": 0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


async def test_events_timeseries(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/events/timeseries?ga=...&from=...&to=... → 200, points."""
    house_id = api_test_data["house_id"]
    ga = api_test_data["ga"]
    resp = await async_client.get(
        f"/api/v1/houses/{house_id}/events/timeseries",
        params={
            "ga": ga,
            "from": "2026-02-28T00:00:00Z",
            "to": "2026-03-01T00:00:00Z",
            "interval": "1h",
            "agg": "avg",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ga"] == ga
    assert "interval" in data
    assert "aggregation" in data
    assert "points" in data


# --- Schemas ---


async def test_schemas_list(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/schemas → 200, items."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/schemas")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) >= 1


async def test_schema_detail(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/schemas/{schema_hash} → 200, objects."""
    house_id = api_test_data["house_id"]
    schema_hash = api_test_data["schema_hash"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/schemas/{schema_hash}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_hash"] == schema_hash
    assert "objects" in data


async def test_schema_not_found(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/schemas/sha256:nonexistent → 404."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/schemas/sha256:nonexistent")
    assert resp.status_code == 404


async def test_schema_diff(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/schemas/diff?from=...&to=... → 200, added, removed, changed."""
    house_id = api_test_data["house_id"]
    schema_hash = api_test_data["schema_hash"]
    resp = await async_client.get(
        f"/api/v1/houses/{house_id}/schemas/diff",
        params={"from": schema_hash, "to": schema_hash},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_hash"] == schema_hash
    assert data["to_hash"] == schema_hash
    assert "added" in data
    assert "removed" in data
    assert "changed" in data


async def test_schemas_house_not_found(async_client: AsyncClient) -> None:
    """GET /api/v1/houses/nonexistent/schemas → 404."""
    resp = await async_client.get("/api/v1/houses/nonexistent/schemas")
    assert resp.status_code == 404


# --- Commands ---


async def test_command_post_single(async_client: AsyncClient, api_test_data: dict) -> None:
    """POST /api/v1/houses/{house_id}/commands (single) → 201, request_id, status=sent."""
    house_id = api_test_data["house_id"]
    ga = api_test_data["ga"]
    resp = await async_client.post(
        f"/api/v1/houses/{house_id}/commands",
        json={"ga": ga, "value": True, "comment": "Тест"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "request_id" in data
    assert data["house_id"] == house_id
    assert data["status"] == "sent"
    assert "ts_sent" in data


async def test_command_post_batch(async_client: AsyncClient, api_test_data: dict) -> None:
    """POST /api/v1/houses/{house_id}/commands (batch) → 201."""
    house_id = api_test_data["house_id"]
    ga = api_test_data["ga"]
    resp = await async_client.post(
        f"/api/v1/houses/{house_id}/commands",
        json={
            "items": [{"ga": ga, "value": True}, {"ga": ga, "value": False}],
            "comment": "Batch",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "request_id" in data
    assert data["status"] == "sent"


async def test_command_post_house_not_found(async_client: AsyncClient) -> None:
    """POST /api/v1/houses/nonexistent/commands → 400."""
    resp = await async_client.post(
        "/api/v1/houses/nonexistent/commands",
        json={"ga": "1/1/1", "value": True},
    )
    assert resp.status_code == 400


async def test_command_post_unknown_ga(async_client: AsyncClient, api_test_data: dict) -> None:
    """POST /api/v1/houses/{house_id}/commands с неизвестным GA → 400."""
    house_id = api_test_data["house_id"]
    resp = await async_client.post(
        f"/api/v1/houses/{house_id}/commands",
        json={"ga": "999/999/999", "value": True},
    )
    assert resp.status_code == 400


async def test_command_post_inactive_house(
    async_client: AsyncClient, api_test_data: dict,
) -> None:
    """POST /api/v1/houses/{house_id}/commands при is_active=False → 400."""
    house_id = api_test_data["house_id"]
    ga = api_test_data["ga"]
    await async_client.patch(f"/api/v1/houses/{house_id}", json={"is_active": False})
    resp = await async_client.post(
        f"/api/v1/houses/{house_id}/commands",
        json={"ga": ga, "value": True},
    )
    assert resp.status_code == 400


async def test_commands_list(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/commands → 200, items, total, limit, offset."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/commands")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


async def test_commands_list_with_filters(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/commands?status=ok&limit=10&offset=0."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(
        f"/api/v1/houses/{house_id}/commands",
        params={"status": "ok", "limit": 10, "offset": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


async def test_command_detail(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/commands/{request_id} → 200."""
    house_id = api_test_data["house_id"]
    request_id = api_test_data["request_id"]
    resp = await async_client.get(f"/api/v1/houses/{house_id}/commands/{request_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_id"] == request_id
    assert "payload" in data
    assert "status" in data


async def test_command_not_found(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/commands/invalid-uuid → 404."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(
        f"/api/v1/houses/{house_id}/commands/550e8400-e29b-41d4-a716-446655440000",
    )
    assert resp.status_code == 404


# --- RPC ---


async def test_rpc_meta(async_client: AsyncClient, api_test_data: dict) -> None:
    """POST /api/v1/houses/{house_id}/devices/{device_id}/rpc/meta → 202, request_id, status."""
    house_id = api_test_data["house_id"]
    device_id = api_test_data["device_id"]
    resp = await async_client.post(
        f"/api/v1/houses/{house_id}/devices/{device_id}/rpc/meta",
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "request_id" in data
    assert data["status"] == "requested"


async def test_rpc_snapshot(async_client: AsyncClient, api_test_data: dict) -> None:
    """POST /api/v1/houses/{house_id}/devices/{device_id}/rpc/snapshot → 202."""
    house_id = api_test_data["house_id"]
    device_id = api_test_data["device_id"]
    resp = await async_client.post(
        f"/api/v1/houses/{house_id}/devices/{device_id}/rpc/snapshot",
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "request_id" in data
    assert data["status"] == "requested"


# --- Pagination (Common) ---


async def test_houses_pagination(async_client: AsyncClient) -> None:
    """GET /api/v1/houses?limit=10&offset=0 → items, total, limit, offset (если поддерживается)."""
    resp = await async_client.get("/api/v1/houses")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


async def test_objects_pagination(async_client: AsyncClient, api_test_data: dict) -> None:
    """GET /api/v1/houses/{house_id}/objects?limit=5&offset=0 → 200."""
    house_id = api_test_data["house_id"]
    resp = await async_client.get(
        f"/api/v1/houses/{house_id}/objects",
        params={"limit": 5, "offset": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
