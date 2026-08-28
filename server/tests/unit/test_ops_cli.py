"""Operator CLI and OpenClaw skill stay aligned with the Ops registry."""

from __future__ import annotations

import json
from pathlib import Path

from cottage_monitoring.ops.catalog import load_catalog
from cottage_monitoring.ops.registry import op_names

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = REPO_ROOT / "skills" / "cottage-monitoring" / "SKILL.md"
AGENTS_CANON = (
    REPO_ROOT / "specs" / "001-server-mqtt-ingestor" / "openclaw-cottage-agent-instructions.md"
)
PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_skill_md_contains_list_houses() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "list_houses" in text
    assert "house_id" in text


def test_agents_canon_duplicates_house_rules() -> None:
    text = AGENTS_CANON.read_text(encoding="utf-8")
    assert "list_houses" in text
    assert "house_id" in text


def test_pyproject_registers_cottage_ops_entry_point() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert 'cottage-ops = "cottage_monitoring.cli.ops_catalog:main"' in text


def test_catalog_cli_names_match_registry(capsys) -> None:
    from cottage_monitoring.cli.ops_catalog import main

    load_catalog()
    expected = list(op_names())

    rc = main(["catalog"])
    assert rc == 0
    printed = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert printed == expected


def test_skill_and_agents_mention_auto_heating_and_kettle_setpoint() -> None:
    skill = SKILL_MD.read_text(encoding="utf-8")
    agents = AGENTS_CANON.read_text(encoding="utf-8")
    for text in (skill, agents):
        assert "set_auto_heating" in text
        assert "setpoint_c" in text
    conn = REPO_ROOT / "skills/cottage-monitoring/references/openclaw-connection.md"
    assert "17" in conn.read_text(encoding="utf-8")


def test_catalog_cli_json_names_match_registry(capsys) -> None:
    from cottage_monitoring.cli.ops_catalog import main

    load_catalog()
    expected = list(op_names())

    rc = main(["catalog", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == expected
