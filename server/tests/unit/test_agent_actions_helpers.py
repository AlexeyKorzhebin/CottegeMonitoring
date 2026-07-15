from types import SimpleNamespace

from cottage_monitoring.services.agent_actions import (
    _appliance_base_name,
    _group_appliances,
    _norm_ga,
)
from cottage_monitoring.services.object_resolver import ObjectRole


def test_norm_ga_dash_to_slash() -> None:
    assert _norm_ga("33-1-13") == "33/1/13"
    assert _norm_ga("33/1/13") == "33/1/13"
    assert _norm_ga("1-7-1") == "1/7/1"


def test_appliance_base_name() -> None:
    assert _appliance_base_name("ble_teapot_RK-M173S_cmd") == "ble_teapot_RK-M173S"
    assert _appliance_base_name("ble_teapot_RK-M173S_temp") == "ble_teapot_RK-M173S"
    assert _appliance_base_name("ble_teapot_RK-M173S_state") == "ble_teapot_RK-M173S"


def test_group_appliances_teapot_summary() -> None:
    matches = [
        SimpleNamespace(
            ga="33/1/39",
            name="ble_teapot_RK-M173S_cmd",
            role=ObjectRole.ZIGBEE_APPLIANCE,
            tags=["ble", "control", "zigbee_send"],
        ),
        SimpleNamespace(
            ga="33/1/37",
            name="ble_teapot_RK-M173S_temp",
            role=ObjectRole.ZIGBEE_APPLIANCE,
            tags=["ble", "teapot", "temp"],
        ),
        SimpleNamespace(
            ga="33/1/38",
            name="ble_teapot_RK-M173S_state",
            role=ObjectRole.ZIGBEE_APPLIANCE,
            tags=["ble", "teapot", "status"],
        ),
    ]
    states = {"33/1/39": True, "33/1/37": 54, "33/1/38": True}
    groups = _group_appliances(matches, states)
    assert len(groups) == 1
    g = groups[0]
    assert g["name"] == "ble_teapot_RK-M173S"
    assert g["cmd_ga"] == "33/1/39"
    assert g["temp_ga"] == "33/1/37"
    assert g["state_ga"] == "33/1/38"
    assert g["on"] is True
    assert g["temp"] == 54
    assert g["state"] is True
