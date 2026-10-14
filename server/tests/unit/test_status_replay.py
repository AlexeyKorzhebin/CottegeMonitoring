"""Restart replay, live LWT and fresh-event recovery without DB/MQTT writes."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cottage_monitoring.mqtt.topic_parser import MessageType
from cottage_monitoring.services import event_service, house_service, ingestor


def msg(kind, payload, retain=False, prefix=''):
    return SimpleNamespace(topic=prefix + 'cm/house/lm-main/v1/' + kind,
                           payload=json.dumps(payload).encode(), retain=retain)


@pytest.mark.parametrize('prefix', ['', 'dev/'])
@pytest.mark.parametrize('order', [('online', 'offline'), ('offline', 'online')])
def test_replay_then_fresh_recovery_then_live_will(monkeypatch, prefix, order):
    monkeypatch.setattr(ingestor.settings, 'mqtt_topic_prefix', '')
    monkeypatch.setattr(ingestor.time, 'time', lambda: 10000)
    device = SimpleNamespace(online_status='offline')
    ensure_house = AsyncMock()
    ensure_device = AsyncMock(return_value=device)
    monkeypatch.setattr(house_service, 'ensure_house', ensure_house)
    monkeypatch.setattr(house_service, 'ensure_device', ensure_device)
    monkeypatch.setattr(house_service, 'is_house_active', AsyncMock(return_value=True))
    monkeypatch.setattr(event_service, 'handle_event', AsyncMock())

    async def set_status(hid, did, payload):
        device.online_status = payload['status']

    status = AsyncMock(side_effect=set_status)
    monkeypatch.setattr(house_service, 'handle_status', status)

    async def scenario():
        for state in order:
            await ingestor.handle_message(msg('status/' + state, {'ts': 1, 'status': state}, True, prefix))
        ensure_house.assert_not_awaited()
        ensure_device.assert_not_awaited()
        status.assert_not_awaited()
        # Replay must not prove recovery; a current live event does.
        await ingestor.handle_message(msg('events', {'ts': 10000, 'ga': '1/1/1', 'value': 1}, False, prefix))
        assert device.online_status == 'online'
        # LWT timestamp is connection-time: still apply live disconnect.
        await ingestor.handle_message(msg('status/offline', {'ts': 1, 'status': 'offline'}, False, prefix))
        assert device.online_status == 'offline'
        # A stale queued event cannot reverse that disconnect.
        await ingestor.handle_message(msg('events', {'ts': 1, 'ga': '1/1/1', 'value': 1}, False, prefix))
        assert device.online_status == 'offline'
        # Another replay after resubscribe also cannot alter it.
        await ingestor.handle_message(msg('status/online', {'ts': 10000, 'status': 'online'}, True, prefix))
        assert device.online_status == 'offline'

    asyncio.run(scenario())
    assert status.await_count == 2


@pytest.mark.parametrize('ts', [1, 10100, None, '10000', True, float('nan'), float('inf')])
def test_stale_or_invalid_events_cannot_prove_online(monkeypatch, ts):
    monkeypatch.setattr(ingestor.time, 'time', lambda: 10000)
    assert not ingestor.is_fresh_live_event(SimpleNamespace(retain=False), MessageType.EVENT,
                                           {'ts': ts, 'ga': '1/1/1', 'value': 0})


def test_batch_and_retained_liveness(monkeypatch):
    monkeypatch.setattr(ingestor.time, 'time', lambda: 10000)
    payload = {'events': [{'ts': 9999, 'ga': '1/1/1', 'value': 0}]}
    assert ingestor.is_fresh_live_event(SimpleNamespace(retain=False), MessageType.EVENT_BATCH, payload)
    assert not ingestor.is_fresh_live_event(SimpleNamespace(retain=True), MessageType.EVENT_BATCH, payload)
    assert not ingestor.is_fresh_live_event(SimpleNamespace(retain=False), MessageType.EVENT_BATCH, {'events': 'bad'})
