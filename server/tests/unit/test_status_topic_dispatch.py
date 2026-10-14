"""Retained health must not refresh telemetry; offline must retain status dispatch."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cottage_monitoring.services import house_service, ingestor


@pytest.mark.parametrize("prefix", ["", "dev/"])
def test_health_diagnostic_does_not_touch_registry(monkeypatch, prefix):
    monkeypatch.setattr(ingestor.settings, "mqtt_topic_prefix", "")
    ensure_house = AsyncMock()
    ensure_device = AsyncMock()
    status = AsyncMock()
    logger = Mock()
    monkeypatch.setattr(house_service, "ensure_house", ensure_house)
    monkeypatch.setattr(house_service, "ensure_device", ensure_device)
    monkeypatch.setattr(house_service, "handle_status", status)
    monkeypatch.setattr(ingestor, "logger", logger)
    msg = SimpleNamespace(topic=prefix + "cm/house/lm-main/v1/status/health", payload=json.dumps({"ts": 1, "status": "online"}).encode())
    asyncio.run(ingestor.handle_message(msg))
    ensure_house.assert_not_awaited()
    ensure_device.assert_not_awaited()
    status.assert_not_awaited()
    logger.warning.assert_not_called()


def test_offline_reaches_existing_status_handler(monkeypatch):
    monkeypatch.setattr(ingestor.settings, "mqtt_topic_prefix", "")
    monkeypatch.setattr(house_service, "ensure_house", AsyncMock())
    monkeypatch.setattr(house_service, "ensure_device", AsyncMock())
    status = AsyncMock()
    monkeypatch.setattr(house_service, "handle_status", status)
    payload = {"ts": 1, "status": "offline"}
    asyncio.run(ingestor.handle_message(SimpleNamespace(topic="cm/house/lm-main/v1/status/offline", payload=json.dumps(payload).encode())))
    status.assert_awaited_once_with("house", "lm-main", payload)
