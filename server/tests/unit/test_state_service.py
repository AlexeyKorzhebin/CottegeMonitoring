from datetime import UTC, datetime

from cottage_monitoring.services.state_service import (
    should_apply_state,
    storage_ga,
    _ga_lookup_keys,
)


def test_storage_ga_slash_to_dash() -> None:
    assert storage_ga("1/2/1") == "1-2-1"
    assert storage_ga("1-2-1") == "1-2-1"
    assert storage_ga("33/1/13") == "33-1-13"


def test_ga_lookup_keys_both_forms() -> None:
    keys = _ga_lookup_keys("1/2/1")
    assert "1-2-1" in keys
    assert "1/2/1" in keys


def test_should_apply_newer_or_equal() -> None:
    older = datetime(2026, 7, 12, 11, 0, tzinfo=UTC)
    newer = datetime(2026, 7, 15, 18, 2, tzinfo=UTC)
    assert should_apply_state(None, newer) is True
    assert should_apply_state(older, newer) is True
    assert should_apply_state(newer, newer) is True
    assert should_apply_state(newer, older) is False
