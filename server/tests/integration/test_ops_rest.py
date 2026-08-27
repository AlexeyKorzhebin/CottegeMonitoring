"""Integration tests for the Ops REST face: GET /ops, POST .../ops/{name}, GET /houses."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.keys import generate_api_key, hash_api_key
from cottage_monitoring.models.api_key import ApiKey
from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.houses import list_houses
from cottage_monitoring.ops.registry import all_ops, op_names
from cottage_monitoring.services.house_service import ensure_house

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _catalog_loaded() -> None:
    """The async_client fixture runs no lifespan, so load the catalog explicitly."""
    load_catalog()


async def _house(session: AsyncSession) -> str:
    """Register a fresh house and commit it: api_keys.house_id is a FK."""
    house_id = f"house-ops-{uuid.uuid4().hex[:12]}"
    await ensure_house(house_id, session=session)
    await session.commit()
    return house_id


async def _make_key(
    session: AsyncSession,
    house_id: str,
    scopes: list[str],
) -> str:
    raw, prefix = generate_api_key()
    session.add(
        ApiKey(
            name=f"ops-test-{uuid.uuid4().hex[:8]}",
            key_prefix=prefix,
            key_hash=hash_api_key(raw),
            house_id=house_id,
            scopes=scopes,
        )
    )
    await session.commit()
    return raw


def _auth_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cottage_monitoring.auth.middleware.settings.auth_required", True)


async def test_list_houses_handler_filters_by_house_ids(db_session: AsyncSession) -> None:
    granted = f"house-ops-{uuid.uuid4().hex[:12]}"
    other = f"house-ops-{uuid.uuid4().hex[:12]}"
    await ensure_house(granted, session=db_session)
    await ensure_house(other, session=db_session)
    await db_session.commit()

    result = await list_houses(db_session, house_ids=frozenset({granted}))

    ids = {item["house_id"] for item in result["items"]}
    assert ids == {granted}
    assert result["total"] == 1


async def test_list_houses_route_auth_off_passes_none_house_ids() -> None:
    """AUTH_REQUIRED=false: route must pass house_ids=None (all houses), not an empty set."""
    from cottage_monitoring.api.houses import list_houses as list_houses_route

    session = AsyncMock()
    with patch(
        "cottage_monitoring.api.houses.list_houses_handler",
        new_callable=AsyncMock,
        return_value={"items": [], "total": 0},
    ) as handler:
        result = await list_houses_route(session=session, ctx=None)

    handler.assert_awaited_once_with(session, house_ids=None)
    assert result == {"items": [], "total": 0}


async def test_list_houses_handler_returns_all_granted_ids(db_session: AsyncSession) -> None:
    a = f"house-ops-{uuid.uuid4().hex[:12]}"
    b = f"house-ops-{uuid.uuid4().hex[:12]}"
    extra = f"house-ops-{uuid.uuid4().hex[:12]}"
    await ensure_house(a, session=db_session)
    await ensure_house(b, session=db_session)
    await ensure_house(extra, session=db_session)
    await db_session.commit()

    result = await list_houses(db_session, house_ids=frozenset({a, b}))

    ids = {item["house_id"] for item in result["items"]}
    assert ids == {a, b}
    assert result["total"] == 2


async def test_get_houses_http_returns_only_granted_house(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    granted = f"house-ops-{uuid.uuid4().hex[:12]}"
    other = f"house-ops-{uuid.uuid4().hex[:12]}"
    await ensure_house(granted, session=db_session)
    await ensure_house(other, session=db_session)

    raw = await _make_key(db_session, granted, ["read"])
    _auth_on(monkeypatch)

    resp = await async_client.get(
        "/api/v1/houses",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["house_id"] for item in data["items"]}
    assert ids == {granted}
    assert data["total"] == 1
    assert other not in ids


# --- GET /api/v1/ops --------------------------------------------------------


async def test_ops_catalog_for_write_key_matches_registry(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = await _house(db_session)
    raw = await _make_key(db_session, house, ["read", "write"])
    _auth_on(monkeypatch)

    resp = await async_client.get("/api/v1/ops", headers={"Authorization": f"Bearer {raw}"})

    assert resp.status_code == 200
    assert {item["name"] for item in resp.json()["items"]} == set(op_names())


async def test_ops_catalog_for_read_key_omits_write_ops(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = await _house(db_session)
    raw = await _make_key(db_session, house, ["read"])
    _auth_on(monkeypatch)

    resp = await async_client.get("/api/v1/ops", headers={"Authorization": f"Bearer {raw}"})

    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()["items"]}
    write_names = {spec.name for spec in all_ops() if spec.permission == "write"}
    assert write_names
    assert not (names & write_names)
    assert "list_lights" in names


# --- POST /api/v1/houses/{house_id}/ops/{name} ------------------------------


async def test_call_op_runs_house_scoped_read_op(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = await _house(db_session)
    raw = await _make_key(db_session, house, ["read"])
    _auth_on(monkeypatch)

    resp = await async_client.post(
        f"/api/v1/houses/{house}/ops/list_lights",
        headers={"Authorization": f"Bearer {raw}"},
        json={},
    )

    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


async def test_call_op_rejects_unknown_op(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = await _house(db_session)
    raw = await _make_key(db_session, house, ["read"])
    _auth_on(monkeypatch)

    resp = await async_client.post(
        f"/api/v1/houses/{house}/ops/make_coffee",
        headers={"Authorization": f"Bearer {raw}"},
        json={},
    )

    assert resp.status_code == 404


async def test_call_op_rejects_non_house_scoped_op(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_houses has its own REST binding (GET /houses); no POST /ops/list_houses."""
    house = await _house(db_session)
    raw = await _make_key(db_session, house, ["read"])
    _auth_on(monkeypatch)

    resp = await async_client.post(
        f"/api/v1/houses/{house}/ops/list_houses",
        headers={"Authorization": f"Bearer {raw}"},
        json={},
    )

    assert resp.status_code == 404


async def test_call_op_rejects_house_id_in_body(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The path segment is the only source of truth for the house."""
    house = await _house(db_session)
    raw = await _make_key(db_session, house, ["read"])
    _auth_on(monkeypatch)

    resp = await async_client.post(
        f"/api/v1/houses/{house}/ops/list_lights",
        headers={"Authorization": f"Bearer {raw}"},
        json={"house_id": "someone-elses-house"},
    )

    assert resp.status_code == 422


async def test_call_op_denies_write_op_for_read_key(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = await _house(db_session)
    raw = await _make_key(db_session, house, ["read"])
    _auth_on(monkeypatch)

    resp = await async_client.post(
        f"/api/v1/houses/{house}/ops/set_light",
        headers={"Authorization": f"Bearer {raw}"},
        json={"query": "кухня", "on": True},
    )

    assert resp.status_code == 403


async def test_call_op_denies_other_house(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    granted = await _house(db_session)
    other = await _house(db_session)
    raw = await _make_key(db_session, granted, ["read"])
    _auth_on(monkeypatch)

    resp = await async_client.post(
        f"/api/v1/houses/{other}/ops/list_lights",
        headers={"Authorization": f"Bearer {raw}"},
        json={},
    )

    assert resp.status_code == 403


async def test_call_op_enforces_write_rate_limit_on_rest(
    db_session: AsyncSession,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The limiter used to live in the MCP wrappers only (design spec §7.4)."""
    house = await _house(db_session)
    raw = await _make_key(db_session, house, ["read", "write"])
    _auth_on(monkeypatch)

    limiter = AsyncMock(
        side_effect=HTTPException(status_code=429, detail="Write rate limit exceeded")
    )
    with patch(
        "cottage_monitoring.ops.dispatch.agent_actions.check_write_rate_limit",
        limiter,
    ):
        resp = await async_client.post(
            f"/api/v1/houses/{house}/ops/set_light",
            headers={"Authorization": f"Bearer {raw}"},
            json={"query": "кухня", "on": True},
        )

    assert resp.status_code == 429
    limiter.assert_awaited_once()
