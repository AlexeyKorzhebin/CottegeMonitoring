import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from cottage_monitoring.api import platform_metrics as receiver
from cottage_monitoring.config import settings
from cottage_monitoring.platform_metrics_app import app


def test_import_and_lifespan_do_not_load_household_app():
    # Fresh interpreter avoids a misleading result from other pytest imports.
    code = """
import sys
from fastapi.testclient import TestClient
from cottage_monitoring.platform_metrics_app import app
with TestClient(app) as client:
    assert client.get('/healthz').json() == {'status': 'ok'}
for name in ('cottage_monitoring.main', 'cottage_monitoring.deps',
             'cottage_monitoring.db.session', 'cottage_monitoring.mcp.server'):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-c", code], check=True, env=os.environ.copy())
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/api/v1/houses").status_code == 404


def test_standalone_preserves_receiver_statuses(monkeypatch, tmp_path):
    token = tmp_path / "token"
    token.write_text("fixture-token")
    monkeypatch.setattr(settings, "platform_metrics_enabled", True)
    monkeypatch.setattr(settings, "platform_metrics_token_file", str(token))
    monkeypatch.setattr(settings, "auth_required", False)
    monkeypatch.setattr(receiver, "_tokens", 10.0)
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "version": 1,
        "batch_id": str(uuid4()),
        "producer": "ai-server",
        "created_at": stamp,
        "samples": [
            {
                "service": "gateway",
                "metric": "ready",
                "unit": "bool",
                "observed_at": stamp,
                "status": "observed",
                "value": 1,
            }
        ],
    }
    result = "accepted"

    async def fake_store(data, digest):
        return result

    monkeypatch.setattr(receiver, "store", fake_store)
    with TestClient(app) as client:
        url = "/api/v1/platform-metrics/batches"
        assert client.post(url, json=body).status_code == 401
        headers = {"Authorization": "Bearer fixture-token"}
        assert client.post(url, json=body, headers=headers).json()["result"] == "accepted"
        result = "duplicate"
        assert client.post(url, json=body, headers=headers).json()["result"] == "duplicate"
        result = "conflict"
        assert client.post(url, json=body, headers=headers).status_code == 409
        assert (
            client.post(
                url,
                content=json.dumps({"prompt": "bad"}),
                headers=headers | {"Content-Type": "application/json"},
            ).status_code
            == 400
        )
        assert (
            client.post(
                url, content=b"x" * 65537, headers=headers | {"Content-Type": "application/json"}
            ).status_code
            == 413
        )
        assert client.get("/api/v1/houses").status_code == 404
