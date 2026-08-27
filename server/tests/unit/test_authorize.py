from uuid import uuid4

import pytest
from fastapi import HTTPException

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.auth.deps import authorize


def _ctx(*houses: str, scopes=("read", "write")) -> ApiKeyContext:
    return ApiKeyContext(
        key_id=uuid4(),
        name="t",
        scopes=frozenset(scopes),
        house_ids=frozenset(houses),
    )


def test_authorize_allows_granted_house():
    authorize(_ctx("h1"), "h1", "read")


def test_authorize_rejects_other_house():
    with pytest.raises(HTTPException) as ei:
        authorize(_ctx("h1"), "h2", "read")
    assert ei.value.status_code == 403


def test_authorize_rejects_missing_write():
    with pytest.raises(HTTPException) as ei:
        authorize(_ctx("h1", scopes=("read",)), "h1", "write")
    assert ei.value.status_code == 403


def test_default_house_id_single_and_many():
    assert _ctx("h1").default_house_id() == "h1"
    assert _ctx("h1", "h2").default_house_id() is None
