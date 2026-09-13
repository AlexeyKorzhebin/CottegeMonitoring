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


def test_generated_ai_srv_dashboard_contains_gas() -> None:
    mod = _load_generate_dashboards()
    dash = mod.ai_srv()
    blob = json.dumps(dash)
    assert dash["uid"] == "cottage-ai-srv"
    assert "35/1/2" in blob
    assert "35/1/1" in blob
    assert any(link.get("url") == "/grafana/d/cottage-ai-srv/" for link in mod.DASH_LINKS)
