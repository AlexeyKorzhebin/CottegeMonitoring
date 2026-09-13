import importlib.util
import json
from pathlib import Path


def _load_generate_dashboards():
    path = Path(__file__).resolve().parents[2] / "deploy/grafana/generate_dashboards.py"
    spec = importlib.util.spec_from_file_location("gd", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _threshold_color(steps: list[dict], value: float) -> str:
    color = steps[0]["color"]
    for step in steps[1:]:
        if value >= step["value"]:
            color = step["color"]
        else:
            break
    return color


def test_generated_ai_srv_dashboard_contains_gas() -> None:
    mod = _load_generate_dashboards()
    dash = mod.ai_srv()
    blob = json.dumps(dash)
    assert dash["uid"] == "cottage-ai-srv"
    assert "35/1/2" in blob
    assert "35/1/1" in blob
    assert any(link.get("url") == "/grafana/d/cottage-ai-srv/" for link in mod.DASH_LINKS)


def test_ai_srv_rpm_thresholds_are_two_sided() -> None:
    mod = _load_generate_dashboards()
    steps = mod.AI_RPM_THRESHOLDS["steps"]
    assert _threshold_color(steps, -1) == "red"
    assert _threshold_color(steps, 0) == "green"
    assert _threshold_color(steps, 1500) == "green"
    assert _threshold_color(steps, 1999) == "green"
    assert _threshold_color(steps, 2500) == "yellow"
    assert _threshold_color(steps, 3500) == "red"
    dash = mod.ai_srv()
    rpm = next(p for p in dash["panels"] if p.get("title") == "RPM")
    assert rpm["fieldConfig"]["defaults"]["thresholds"] == mod.AI_RPM_THRESHOLDS
    assert rpm["options"]["colorMode"] == "background"


def test_ai_srv_pwm_thresholds_match_rpm_shape() -> None:
    mod = _load_generate_dashboards()
    steps = mod.AI_PWM_THRESHOLDS["steps"]
    assert _threshold_color(steps, -1) == "red"
    assert _threshold_color(steps, 0) == "green"
    assert _threshold_color(steps, 77) == "green"
    assert _threshold_color(steps, 150) == "yellow"
    assert _threshold_color(steps, 180) == "red"
    assert _threshold_color(steps, 255) == "red"
    dash = mod.ai_srv()
    pwm = next(p for p in dash["panels"] if p.get("title") == "PWM")
    assert pwm["fieldConfig"]["defaults"]["thresholds"] == mod.AI_PWM_THRESHOLDS
    assert pwm["options"]["colorMode"] == "background"


def test_ai_srv_temp_thresholds() -> None:
    mod = _load_generate_dashboards()
    steps = mod.AI_TEMP_THRESHOLDS["steps"]
    assert _threshold_color(steps, -1) == "red"
    assert _threshold_color(steps, 45) == "green"
    assert _threshold_color(steps, 59.9) == "green"
    assert _threshold_color(steps, 60) == "yellow"
    assert _threshold_color(steps, 74.9) == "yellow"
    assert _threshold_color(steps, 75) == "orange"
    assert _threshold_color(steps, 80) == "orange"
    assert _threshold_color(steps, 80.1) == "red"
    assert _threshold_color(steps, 84) == "red"
    dash = mod.ai_srv()
    temp = next(p for p in dash["panels"] if p.get("title") == "Температура")
    assert temp["fieldConfig"]["defaults"]["thresholds"] == mod.AI_TEMP_THRESHOLDS
    assert temp["options"]["colorMode"] == "background"
