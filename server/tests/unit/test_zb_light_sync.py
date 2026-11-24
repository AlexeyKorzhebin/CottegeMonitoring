from pathlib import Path
import re
import shutil
import subprocess

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cm-client/scripts/zb_light_sync.lua"
_HARNESS = Path(__file__).with_name("zb_light_sync_harness.lua")
_CATALOG = _REPO / "cm-client/scripts/zb_ceiling_light_catalog.json"

_SECRET_RE = re.compile(
    r"(password\s*=|mqtt_password|login_set\s*\()",
    re.IGNORECASE,
)


def test_script_exists_and_has_no_secrets() -> None:
    assert _SCRIPT.is_file()
    text = _SCRIPT.read_text(encoding="utf-8")
    assert _SECRET_RE.search(text) is None
    assert "zb_light_sync" in text
    assert "Event" in text or "event" in text
    assert "ZB_CEILING_PUBLISH" in text
    assert "zb_light_from_sync_align" in text
    for ga in ("1/1/13", "1/1/14", "1/1/15", "34/1/1", "34/1/4", "34/1/7"):
        assert ga in text
    assert "Ceiling_lamps_tima" in text
    assert "Ceiling_lamp_hall_2_floor" in text
    assert "Ceiling_lamp_office" in text


def test_script_covers_catalog_relays_and_params() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    catalog = _CATALOG.read_text(encoding="utf-8")
    for ga in (
        "34/1/1",
        "34/2/1",
        "34/1/2",
        "34/2/2",
        "34/1/3",
        "34/2/3",
        "34/1/4",
        "34/2/4",
        "34/1/5",
        "34/2/5",
        "34/1/6",
        "34/2/6",
        "34/1/7",
        "34/2/7",
        "34/1/8",
        "34/2/8",
        "34/1/9",
        "34/2/9",
    ):
        assert ga in catalog
        assert ga in text


def test_lww_harness() -> None:
    lua = shutil.which("lua")
    assert lua, "lua interpreter required for zb_light_sync LWW tests"
    result = subprocess.run(
        [lua, str(_HARNESS), str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL PASS" in result.stdout
