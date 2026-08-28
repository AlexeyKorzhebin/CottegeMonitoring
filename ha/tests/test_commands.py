from __future__ import annotations

import ast
import asyncio
from pathlib import Path

from cottage_monitoring.commands import (
    auto_heating_body,
    climate_set_temp_body,
    kettle_off_body,
    kettle_on_body,
    kettle_setpoint_body,
    lights_turn_off_body,
    lights_turn_on_body,
)

COMMANDS_PY = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "cottage_monitoring"
    / "commands.py"
)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_climate_body_has_no_force_relay() -> None:
    name, body = climate_set_temp_body("кухня", 22)
    assert name == "set_climate"
    assert "force_relay" not in body
    assert body == {"query": "кухня", "setpoint_c": 22}


def test_light_uses_set_lights_not_set_light() -> None:
    name, body = lights_turn_on_body("Свет - кухня")
    assert name == "set_lights"
    assert body["skip_unchanged"] is True


def test_lights_turn_on_body() -> None:
    name, body = lights_turn_on_body("Свет - кухня")
    assert name == "set_lights"
    assert body == {"query": "Свет - кухня", "on": True, "skip_unchanged": True}


def test_lights_turn_off_body() -> None:
    name, body = lights_turn_off_body("Свет - кухня")
    assert name == "set_lights"
    assert body == {"query": "Свет - кухня", "on": False, "skip_unchanged": True}


def test_auto_heating_body() -> None:
    assert auto_heating_body(True) == ("set_auto_heating", {"on": True})
    assert auto_heating_body(False) == ("set_auto_heating", {"on": False})


def test_kettle_on_body() -> None:
    assert kettle_on_body() == ("set_kettle", {"on": True})


def test_kettle_off_body() -> None:
    assert kettle_off_body() == ("set_kettle", {"on": False})


def test_kettle_setpoint_body() -> None:
    name, body = kettle_setpoint_body(80)
    assert name == "set_kettle"
    assert body == {"setpoint_c": 80}
    assert "on" not in body


def test_commands_module_does_not_import_homeassistant() -> None:
    for module in _imported_modules(COMMANDS_PY):
        assert not module.startswith("homeassistant")
    for module in _imported_modules(Path(__file__)):
        assert not module.startswith("homeassistant")


class FakeClient:
    def __init__(self) -> None:
        self.ops: list[tuple[str, dict]] = []

    async def call_op(self, name: str, body: dict | None = None) -> dict:
        self.ops.append((name, dict(body or {})))
        return {}


class FakeCoordinator:
    def __init__(self) -> None:
        self.client = FakeClient()

    async def send(self, helper, *args):
        name, body = helper(*args)
        await self.client.call_op(name, body)
        return name, body


def test_fake_coordinator_call_op_bodies() -> None:
    coord = FakeCoordinator()

    async def _run() -> None:
        await coord.send(lights_turn_on_body, "Свет - кухня")
        await coord.send(climate_set_temp_body, "гостиная 1", 23.0)
        await coord.send(auto_heating_body, False)
        await coord.send(kettle_on_body)
        await coord.send(kettle_setpoint_body, 80.0)

    asyncio.run(_run())
    assert coord.client.ops == [
        ("set_lights", {"query": "Свет - кухня", "on": True, "skip_unchanged": True}),
        ("set_climate", {"query": "гостиная 1", "setpoint_c": 23.0}),
        ("set_auto_heating", {"on": False}),
        ("set_kettle", {"on": True}),
        ("set_kettle", {"setpoint_c": 80.0}),
    ]
    assert all("force_relay" not in body for _, body in coord.client.ops)
