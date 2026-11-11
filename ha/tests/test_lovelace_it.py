from pathlib import Path

HA_DEPLOY = Path(__file__).resolve().parents[2] / "server" / "deploy" / "ha"


def test_configuration_registers_it_dashboard() -> None:
    src = (HA_DEPLOY / "configuration.yaml").read_text(encoding="utf-8")
    assert "cottage-it:" in src
    assert "title: ИТ" in src
    assert "filename: dashboards/it.yaml" in src
    assert "title: Бытовая техника" in src
    assert "filename: dashboards/appliances.yaml" in src


def test_it_dashboard_has_projector_and_plug() -> None:
    src = (HA_DEPLOY / "dashboards" / "it.yaml").read_text(encoding="utf-8")
    assert src.splitlines()[0] == "title: ИТ"
    assert "switch.projector" in src
    assert "switch.ai_srv" in src
    assert "sensor.ai_srv_power" in src
    assert "sensor.ai_srv_current" in src
    assert "sensor.ai_srv_voltage" in src
    assert "sensor.ai_srv_energy" in src
    assert "water_heater.ble_teapot_rk_m173s" not in src


def test_appliances_dashboard_stays_kettle_only() -> None:
    src = (HA_DEPLOY / "dashboards" / "appliances.yaml").read_text(encoding="utf-8")
    assert "water_heater.ble_teapot_rk_m173s" in src
    assert "switch.projector" not in src
    assert "switch.ai_srv" not in src
    assert "Проектор" not in src
    assert "AI-SRV" not in src
