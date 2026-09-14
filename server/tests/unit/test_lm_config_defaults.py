from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def test_apply_lowload_is_heal_profile() -> None:
    src = (_ROOT / "cm-client/apply_lowload.lp").read_text(encoding="utf-8")
    assert "snapshot_interval" in src
    assert "300" in src
    assert "event_sleep" in src
    # must not re-enable handler sleep / light-dropping throttle
    assert "throttle', 20" not in src and 'throttle", 20' not in src
    assert "event_sleep', 0.03" not in src and 'event_sleep", 0.03' not in src


def test_index_lowload_button_heal_values() -> None:
    src = (_ROOT / "cm-client/index.lp").read_text(encoding="utf-8")
    assert "-throttle').val(0)" in src or '-throttle").val(0)' in src
    assert "-event_sleep').val(0)" in src or '-event_sleep").val(0)' in src
    assert "-snapshot_interval').val(300)" in src or '-snapshot_interval").val(300)' in src


def test_health_exposes_drop_counters() -> None:
    src = (_ROOT / "cm-client/health_get.lp").read_text(encoding="utf-8")
    assert "cm_dropped_throttle" in src
    assert "cm_dropped_nofind" in src
    assert "cm_last_snapshot_ts" in src
