"""House resolve table from the Nord Ops design spec §9."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.ops.resolve_house import resolve_house_id


def _ctx(*houses: str) -> ApiKeyContext:
    return ApiKeyContext(
        key_id=uuid4(),
        name="t",
        scopes=frozenset({"read", "write"}),
        house_ids=frozenset(houses),
    )


def test_not_house_scoped_returns_none() -> None:
    assert resolve_house_id(_ctx("h1"), False, None) is None


def test_not_house_scoped_ignores_requested_house() -> None:
    assert resolve_house_id(_ctx("h1", "h2"), False, "h2") is None


def test_single_grant_without_argument_uses_that_house() -> None:
    assert resolve_house_id(_ctx("h1"), True, None) == "h1"


def test_single_grant_with_matching_argument() -> None:
    assert resolve_house_id(_ctx("h1"), True, "h1") == "h1"


def test_single_grant_with_other_house_is_forbidden() -> None:
    with pytest.raises(HTTPException) as ei:
        resolve_house_id(_ctx("h1"), True, "h2")
    assert ei.value.status_code == 403


def test_no_grants_without_argument_is_forbidden() -> None:
    with pytest.raises(HTTPException) as ei:
        resolve_house_id(_ctx(), True, None)
    assert ei.value.status_code == 403


def test_no_grants_with_argument_is_forbidden() -> None:
    with pytest.raises(HTTPException) as ei:
        resolve_house_id(_ctx(), True, "h1")
    assert ei.value.status_code == 403


def test_two_grants_without_argument_requires_house_id() -> None:
    with pytest.raises(HTTPException) as ei:
        resolve_house_id(_ctx("h1", "h2"), True, None)
    assert ei.value.status_code == 400
    assert ei.value.detail == "house_id required"


def test_two_grants_with_granted_house() -> None:
    assert resolve_house_id(_ctx("h1", "h2"), True, "h2") == "h2"


def test_two_grants_with_ungranted_house_is_forbidden() -> None:
    with pytest.raises(HTTPException) as ei:
        resolve_house_id(_ctx("h1", "h2"), True, "h3")
    assert ei.value.status_code == 403
