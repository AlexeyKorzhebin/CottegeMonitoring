"""Integration tests for Ops REST: GET /houses grant filter (more in later tasks)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.keys import generate_api_key, hash_api_key
from cottage_monitoring.models.api_key import ApiKey
from cottage_monitoring.ops.houses import list_houses
from cottage_monitoring.services.house_service import ensure_house

pytestmark = pytest.mark.integration


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

    raw, prefix = generate_api_key()
    db_session.add(
        ApiKey(
            name=f"ops-test-{uuid.uuid4().hex[:8]}",
            key_prefix=prefix,
            key_hash=hash_api_key(raw),
            house_id=granted,
            scopes=["read"],
        )
    )
    await db_session.commit()

    monkeypatch.setattr(
        "cottage_monitoring.auth.middleware.settings.auth_required",
        True,
    )

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
