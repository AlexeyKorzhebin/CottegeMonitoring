import ast
from pathlib import Path

COORD = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "cottage_monitoring"
    / "coordinator.py"
)
SENSOR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "cottage_monitoring"
    / "sensor.py"
)


def test_coordinator_polls_energy_and_battery() -> None:
    src = COORD.read_text(encoding="utf-8")
    assert 'call_op("get_energy_status")' in src or "call_op('get_energy_status')" in src
    assert '{"kind": "battery"}' in src or "{'kind': 'battery'}" in src
    assert '{"kind": "humidity"}' in src or "{'kind': 'humidity'}" in src
    tree = ast.parse(src)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "call_op"
    ]
    op_names = []
    for call in calls:
        if call.args and isinstance(call.args[0], ast.Constant):
            op_names.append(call.args[0].value)
    assert op_names.count("get_sensors") == 2
    assert "get_energy_status" in op_names
    assert "get_ai_srv_switcher" in op_names
    assert "get_projector" in op_names
    assert "get_kettle" in op_names


def test_sensor_platform_uses_ha_profile_kinds() -> None:
    src = SENSOR.read_text(encoding="utf-8")
    assert "sensor_ha_profile" in src
    assert "UnitOfEnergy" in src
    assert "UnitOfPower" in src
    assert "UnitOfFrequency" in src
    assert "TOTAL_INCREASING" in src
    assert "UnitOfElectricCurrent" in src
    assert "UnitOfElectricPotential" in src


def test_switch_platform_keeps_auto_heating_and_adds_it_switches() -> None:
    switch_py = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "cottage_monitoring"
        / "switch.py"
    )
    src = switch_py.read_text(encoding="utf-8")
    assert "CottageAutoHeatingSwitch" in src
    assert "auto_heating_body" in src
    assert "ai_srv_switcher_body" in src
    assert "projector_body" in src
    assert "set_ai_srv_switcher" in src or "ai_srv_switcher_body" in src
    assert 'entity_id = "switch.ai_srv"' in src
    assert 'entity_id = "switch.projector"' in src
