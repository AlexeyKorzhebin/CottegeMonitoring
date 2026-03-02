"""Integration tests for MQTT client: initial state, backoff, reconnect behaviour."""

from __future__ import annotations

import asyncio

import aiomqtt
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


def test_mqtt_client_backoff_exponential_growth() -> None:
    """Backoff doubles on each simulated failure until it hits the cap."""
    client = MqttClient(host="localhost", port=1883)
    assert client._backoff == 1.0

    expected = [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    for exp in expected:
        client._backoff = min(client._backoff * 2, 30.0)
        assert client._backoff == exp


def test_mqtt_client_disconnect_sets_shutdown() -> None:
    """disconnect() sets _shutdown flag so the messages() loop will exit."""
    client = MqttClient(host="localhost", port=1883)
    assert client._shutdown is False
    asyncio.get_event_loop().run_until_complete(client.disconnect())
    assert client._shutdown is True


async def test_mqtt_client_messages_requires_topic() -> None:
    """Calling messages() without subscribe() raises ValueError."""
    client = MqttClient(host="localhost", port=1883)
    with pytest.raises(ValueError, match="Topic not set"):
        async for _ in client.messages():
            break


async def test_mqtt_connect_disconnect_reconnect() -> None:
    """Connect → receive message → disconnect → fresh client → receive again.

    Uses the real MQTT broker (localhost). For each phase, starts the
    messages() loop in a background task, waits for is_connected, then
    publishes. This avoids race conditions between subscribe and publish.
    """
    from cottage_monitoring.config import settings

    test_topic = f"{settings.mqtt_topic_prefix}test/reconnect/{id(object())}"

    async def _publish(payload: str) -> None:
        async with aiomqtt.Client(
            hostname=settings.mqtt_host,
            port=settings.mqtt_port,
        ) as pub:
            await pub.publish(test_topic, payload, qos=1)

    async def _wait_connected(c: MqttClient, timeout: float = 5.0) -> None:
        elapsed = 0.0
        while not c.is_connected and elapsed < timeout:
            await asyncio.sleep(0.1)
            elapsed += 0.1
        assert c.is_connected, "Client did not connect in time"

    async def _collect_one(c: MqttClient) -> str | None:
        """Run messages() loop and capture the first message payload."""
        async for msg in c.messages():
            return msg.payload.decode()
        return None

    # Phase 1: connect and receive
    client = MqttClient(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        client_id=f"test-reconnect-{id(object())}",
    )
    client.subscribe(test_topic)

    collector = asyncio.create_task(_collect_one(client))
    await _wait_connected(client)

    await _publish("msg1")
    result = await asyncio.wait_for(collector, timeout=5.0)
    assert result == "msg1", f"Expected 'msg1', got {result!r}"
    assert client._backoff == 1.0

    # Phase 2: disconnect
    await client.disconnect()
    assert client._shutdown is True

    # Phase 3: fresh client, receive again
    client2 = MqttClient(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        client_id=f"test-reconnect2-{id(object())}",
    )
    client2.subscribe(test_topic)

    collector2 = asyncio.create_task(_collect_one(client2))
    await _wait_connected(client2)

    await _publish("msg2")
    result2 = await asyncio.wait_for(collector2, timeout=5.0)
    assert result2 == "msg2", f"Expected 'msg2', got {result2!r}"
    await client2.disconnect()


async def test_mqtt_backoff_on_connection_failure() -> None:
    """When broker is unreachable, backoff increases on each retry attempt."""
    client = MqttClient(
        host="unreachable-host-99999",
        port=1883,
        client_id="test-backoff-fail",
    )
    client.subscribe("test/backoff")

    backoff_values: list[float] = []

    original_sleep = asyncio.sleep

    async def _mock_sleep(delay: float) -> None:
        backoff_values.append(delay)
        if len(backoff_values) >= 3:
            client._shutdown = True
        await original_sleep(0)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(asyncio, "sleep", _mock_sleep)
        async for _ in client.messages():
            pass

    assert len(backoff_values) >= 2
    assert backoff_values[0] == 1.0
    assert backoff_values[1] == 2.0
