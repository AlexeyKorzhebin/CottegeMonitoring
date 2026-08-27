"""send_command records the acting API key when request context is set."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.context import ApiKeyContext, api_key_context_var
from cottage_monitoring.auth.keys import generate_api_key, hash_api_key
from cottage_monitoring.models.api_key import ApiKey
from cottage_monitoring.models.command import Command
from cottage_monitoring.services.command_service import send_command
from cottage_monitoring.services.house_service import ensure_house

pytestmark = pytest.mark.integration


async def _make_key(session: AsyncSession, house_id: str) -> ApiKey:
    raw, prefix = generate_api_key()
    key = ApiKey(
        name=f"actor-test-{uuid4().hex[:8]}",
        key_prefix=prefix,
        key_hash=hash_api_key(raw),
        house_id=house_id,
        scopes=["read", "write"],
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return key


async def test_send_command_dry_run_stores_actor_key_id(
    db_session: AsyncSession,
) -> None:
    house_id = f"house-actor-{uuid4().hex[:8]}"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()
    key = await _make_key(db_session, house_id)

    ctx = ApiKeyContext(
        key_id=key.id,
        name=key.name,
        scopes=frozenset(key.scopes),
        house_ids=frozenset({house_id}),
    )
    token = api_key_context_var.set(ctx)
    try:
        cmd = await send_command(
            house_id,
            "lm-main",
            {"ga": "1/1/1", "value": True},
            session=db_session,
            dry_run=True,
        )
        await db_session.commit()
    finally:
        api_key_context_var.reset(token)

    assert cmd.status == "dry_run"
    assert cmd.actor_key_id == key.id

    loaded = await db_session.get(Command, cmd.request_id)
    assert loaded is not None
    assert loaded.actor_key_id == key.id


async def test_send_command_dry_run_leaves_actor_key_id_null_without_context(
    db_session: AsyncSession,
) -> None:
    house_id = f"house-actor-none-{uuid4().hex[:8]}"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    cmd = await send_command(
        house_id,
        "lm-main",
        {"ga": "1/1/1", "value": True},
        session=db_session,
        dry_run=True,
    )
    await db_session.commit()

    assert cmd.status == "dry_run"
    assert cmd.actor_key_id is None
