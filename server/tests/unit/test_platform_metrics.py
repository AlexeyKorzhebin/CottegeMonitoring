import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cottage_monitoring.api import platform_metrics as pm
from cottage_monitoring.auth.middleware import ApiKeyAuthMiddleware
from cottage_monitoring.config import settings


@pytest.fixture
def payload():
    now = datetime.now(UTC).replace(microsecond=0)
    stamp = now.isoformat().replace("+00:00", "Z")
    return {
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


def test_validation_boundaries_and_untrusted_fields(payload):
    now = datetime.now(UTC)
    pm.validate(json.dumps(payload).encode(), now)
    for change in (
        lambda p: p.update(extra="secret"),
        lambda p: p["samples"][0].update(value=True),
        lambda p: p["samples"][0].update(value=float("nan")),
        lambda p: p["samples"][0].update(status="unknown", value=0),
        lambda p: p["samples"].append(dict(p["samples"][0])),
        lambda p: p["samples"][0].update(metric="raw_prompt"),
        lambda p: p.update(created_at=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z")),
    ):
        p = json.loads(json.dumps(payload))
        change(p)
        with pytest.raises((ValueError, TypeError)):
            pm.validate(json.dumps(p).encode(), now)
    payload["samples"][0].update(status="unknown", value=None)
    pm.validate(json.dumps(payload).encode(), now)


@pytest.mark.parametrize("metric,unit,maximum", [
    ("ready", "bool", 1), ("active", "count", 100000),
    ("requests_total_window", "count", 1000000),
    ("errors_total_window", "count", 1000000),
    ("busy_total_window", "count", 1000000),
    ("latency_mean_ms", "ms", 3600000),
])
def test_admission_series_allowlist_and_bounds(payload, metric, unit, maximum):
    sample = payload["samples"][0]
    sample.update(service="admission", metric=metric, unit=unit, value=maximum)
    now = datetime.now(UTC)
    pm.validate(json.dumps(payload).encode(), now)
    sample.update(status="unknown", value=None)
    pm.validate(json.dumps(payload).encode(), now)
    sample.update(status="observed", value=maximum + 1)
    with pytest.raises(ValueError):
        pm.validate(json.dumps(payload).encode(), now)
    sample.update(value=0, unit="unexpected")
    with pytest.raises(ValueError):
        pm.validate(json.dumps(payload).encode(), now)


@pytest.mark.parametrize("house_auth", [False, True])
def test_endpoint_auth_limits_and_errors(monkeypatch, tmp_path, payload, house_auth):
    token = tmp_path / "token"
    token.write_text("writer-secret")
    monkeypatch.setattr(settings, "platform_metrics_enabled", True)
    monkeypatch.setattr(settings, "platform_metrics_token_file", str(token))
    monkeypatch.setattr(settings, "auth_required", house_auth)
    monkeypatch.setattr(pm, "_tokens", 10.0)
    app = FastAPI()
    app.add_middleware(ApiKeyAuthMiddleware)
    app.include_router(pm.router, prefix="/api/v1")

    async def fake_store(data, digest):
        return "accepted"

    monkeypatch.setattr(pm, "store", fake_store)
    client = TestClient(app)
    url = "/api/v1/platform-metrics/batches"
    assert client.post(url, json=payload).status_code == 401
    auth = {"Authorization": "Bearer writer-secret"}
    assert client.post(url, json=payload, headers=auth).json()["result"] == "accepted"
    assert (
        client.post(
            url, content=b"{" + b"x" * 65536, headers={**auth, "Content-Type": "application/json"}
        ).status_code
        == 413
    )
    response = client.post(
        url,
        content='{"secret":"writer-secret"}',
        headers={**auth, "Content-Type": "application/json"},
    )
    assert response.status_code == 400 and "writer-secret" not in response.text
    if house_auth:
        assert client.get(url, headers=auth).status_code == 401
        assert client.post(url + "/other", headers=auth).status_code == 401
    monkeypatch.setattr(pm, "_tokens", 0.0)
    assert client.post(url, json=payload, headers=auth).status_code == 429


def test_conflict_and_store_failure_are_redacted(monkeypatch, tmp_path, payload):
    token = tmp_path / "token"
    token.write_text("secret")
    monkeypatch.setattr(settings, "platform_metrics_enabled", True)
    monkeypatch.setattr(settings, "platform_metrics_token_file", str(token))
    monkeypatch.setattr(pm, "_tokens", 10.0)
    app = FastAPI()
    app.include_router(pm.router, prefix="/api/v1")
    client = TestClient(app)

    async def conflict(*args):
        return "conflict"

    monkeypatch.setattr(pm, "store", conflict)
    assert (
        client.post(
            "/api/v1/platform-metrics/batches",
            json=payload,
            headers={"Authorization": "Bearer secret"},
        ).status_code
        == 409
    )

    async def failed(*args):
        raise RuntimeError("secret")

    monkeypatch.setattr(pm, "store", failed)
    response = client.post(
        "/api/v1/platform-metrics/batches", json=payload, headers={"Authorization": "Bearer secret"}
    )
    assert response.status_code == 503 and "secret" not in response.text
