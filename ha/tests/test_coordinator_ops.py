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


def test_sensor_platform_uses_ha_profile_kinds() -> None:
    src = SENSOR.read_text(encoding="utf-8")
    assert "sensor_ha_profile" in src
    assert "UnitOfEnergy" in src
    assert "UnitOfPower" in src
    assert "UnitOfFrequency" in src
    assert "TOTAL_INCREASING" in src
