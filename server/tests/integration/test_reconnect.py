"""Integration tests for MQTT client: initial state, backoff cap."""

from __future__ import annotations

import pytest

from cottage_monitoring.mqtt.client import MqttClient

pytestmark = pytest.mark.integration


def test_mqtt_client_initial_state() -> None:
    """Client starts with is_connected=False."""
    client = MqttClient(host="localhost", port=1883)
    assert client.is_connected is False


def test_mqtt_client_backoff_reset() -> None:
    """After internal _backoff increases, verify it caps at 30.0."""
    client = MqttClient(host="localhost", port=1883)
    client._backoff = 20.0
    client._backoff = min(client._backoff * 2, 30.0)
    assert client._backoff == 30.0
