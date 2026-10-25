from pathlib import Path

_DAEMON = Path(__file__).resolve().parents[3] / "cm-client/daemon/daemon.lua"


def _src() -> str:
    return _DAEMON.read_text(encoding="utf-8")


def test_version_114() -> None:
    assert "1.1.4" in _src()


def test_listens_groupresponse_and_groupwrite() -> None:
    src = _src()
    assert "sethandler('groupwrite'" in src
    assert "sethandler('groupresponse'" in src
    assert "sethandler('groupread'" not in src


def test_force_export_and_snapshot_interval() -> None:
    src = _src()
    assert "force_export" in src
    assert "snapshot_interval" in src
    assert "cfg('snapshot_interval', 300)" in src or 'cfg("snapshot_interval", 300)' in src
    assert "cfg('event_sleep', 0)" in src or 'cfg("event_sleep", 0)' in src
    assert "cfg('throttle', 0)" in src or 'cfg("throttle", 0)' in src


def test_handler_does_not_sleep() -> None:
    src = _src()
    # event_sleep may still exist as config but must not os.sleep inside handle_bus_event
    start = src.find("local function handle_bus_event")
    assert start != -1
    rest = src[start:]
    end = rest.find("\nlb:sethandler")
    body = rest[:end]
    assert "os.sleep" not in body


def test_throttle_drop_is_counted() -> None:
    src = _src()
    assert "dropped_throttle" in src
    assert "dropped_nofind" in src
