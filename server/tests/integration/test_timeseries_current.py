"""Integration tests for electric meter time series: 30 min @ 30 sec interval → events table.

Covers: voltage (Urms L1/L2/L3), current (Irms L1/L2/L3), power (P L1/L2/L3, Total P),
and energy (AP L1/L2/L3, Total AP, consumption Hour/Daily/Total).

Based on docs/objects.json and specs/001-server-mqtt-ingestor/research.md.

Two test modes:
- test_timeseries_meter_full_30min_stored_correctly: direct handle_event() call (no MQTT)
- test_timeseries_via_mqtt_full_path: full path MQTT publish → ingestor → events table
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import aiomqtt
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.config import settings
from cottage_monitoring.models.event import Event
from cottage_monitoring.services.event_service import handle_event
from cottage_monitoring.services.house_service import ensure_house

pytestmark = pytest.mark.integration

# Meter objects from docs/objects.json (32/1/*, datatype 14)
METER_SERIES = [
    # Voltage Urms (V)
    {"ga": "32/1/1", "id": 65793, "name": "electric meter - Urms L1"},
    {"ga": "32/1/3", "id": 65795, "name": "electric meter - Urms L2"},
    {"ga": "32/1/5", "id": 65797, "name": "electric meter - Urms L3"},
    # Current Irms (A)
    {"ga": "32/1/11", "id": 65803, "name": "electric meter - Irms L1"},
    {"ga": "32/1/19", "id": 65811, "name": "electric meter - Irms L2"},
    {"ga": "32/1/27", "id": 65819, "name": "electric meter - Irms L3"},
    # Power P (W)
    {"ga": "32/1/13", "id": 65805, "name": "electric meter - P L1"},
    {"ga": "32/1/21", "id": 65813, "name": "electric meter - P L2"},
    {"ga": "32/1/29", "id": 65821, "name": "electric meter - P L3"},
    {"ga": "32/1/35", "id": 65827, "name": "electric meter - Total P"},
    # Energy AP (kWh)
    {"ga": "32/1/17", "id": 65809, "name": "electric meter - AP energy L1"},
    {"ga": "32/1/25", "id": 65817, "name": "electric meter - AP energy L2"},
    {"ga": "32/1/33", "id": 65825, "name": "electric meter - AP energy L3"},
    {"ga": "32/1/39", "id": 65831, "name": "electric meter - Total  AP energy"},
    # Consumption
    {"ga": "32/1/57", "id": 65849, "name": "energy meter - consumption Hour"},
    {"ga": "32/1/58", "id": 65850, "name": "energy meter - consumption Daily"},
    {"ga": "32/1/59", "id": 65851, "name": "energy_meter - consumption Total"},
]
DATATYPE = 14  # float32

# 30 minutes = 1800 sec, every 30 sec = 60 points
INTERVAL_SEC = 30
TOTAL_MINUTES = 30
EXPECTED_POINTS = (TOTAL_MINUTES * 60) // INTERVAL_SEC  # 60


def _make_event_payload(
    base_ts: int,
    index: int,
    ga: str,
    object_id: int,
    name: str,
    value: float,
) -> dict:
    """Build event payload for meter object."""
    ts = base_ts + index * INTERVAL_SEC
    return {
        "ts": ts,
        "seq": 1000 + index,
        "type": "knx.groupwrite",
        "ga": ga,
        "id": object_id,
        "name": name,
        "datatype": DATATYPE,
        "value": value,
    }


def _value_for_name(name: str, index: int) -> float:
    """Generate realistic value per object name (from objects.json)."""
    if "Urms" in name:
        return 220 + 15 * (index % 13) / 13  # ~220–235 V
    if "Irms" in name:
        return 0.4 + 15 * (index % 10) / 100  # ~0.4–1.9 A
    if "Total P" in name or (" P L" in name and "Total" not in name):
        return 500 + 3000 * (index % 12) / 12  # ~500–3500 W
    if "AP energy" in name or "Total  AP" in name:
        base = 20000 if "Total" in name else 15000 + hash(name) % 5000
        return base + index * 0.01  # Counter: monotonically increasing
    if "consumption Hour" in name:
        return 1.5 + (index % 6) * 0.2  # ~1.5–2.7 kWh
    if "consumption Daily" in name:
        return 70 + (index % 15)  # ~70–85 kWh
    if "consumption Total" in name:
        return 63000 + index * 0.05  # Counter
    return 0.0


async def test_timeseries_meter_full_30min_stored_correctly(
    db_session: AsyncSession,
) -> None:
    """
    Simulate voltage, current, power, and energy arriving every 30 seconds for 30 minutes.
    All phases + Total. Verify all points stored correctly in events table.
    """
    house_id = f"house-ts-meter-{uuid.uuid4().hex[:12]}"
    await ensure_house(house_id, session=db_session)
    await db_session.commit()

    base_ts = 1730000000
    expected_by_ga: dict[str, list[float]] = {m["ga"]: [] for m in METER_SERIES}

    # Generate 60 events per GA (17 GAs × 60 = 1020 events)
    for i in range(EXPECTED_POINTS):
        for obj in METER_SERIES:
            value = _value_for_name(obj["name"], i)
            expected_by_ga[obj["ga"]].append(value)
            payload = _make_event_payload(
                base_ts, i,
                ga=obj["ga"],
                object_id=obj["id"],
                name=obj["name"],
                value=value,
            )
            await handle_event(house_id, "lm-main", payload, session=db_session)
    await db_session.commit()

    # Verify total event count
    result = await db_session.execute(
        select(func.count()).select_from(Event).where(Event.house_id == house_id)
    )
    total = result.scalar_one()
    expected_total = len(METER_SERIES) * EXPECTED_POINTS
    assert total == expected_total, (
        f"Expected {expected_total} events, got {total}"
    )

    # Verify each GA: count, ts order, values
    for obj in METER_SERIES:
        ga = obj["ga"]
        result = await db_session.execute(
            select(Event)
            .where(Event.house_id == house_id, Event.ga == ga)
            .order_by(Event.ts.asc())
        )
        rows = result.scalars().all()
        assert len(rows) == EXPECTED_POINTS, (
            f"GA {ga}: expected {EXPECTED_POINTS} events, got {len(rows)}"
        )

        for i, row in enumerate(rows):
            expected_ts = datetime.fromtimestamp(
                base_ts + i * INTERVAL_SEC, tz=UTC
            )
            assert row.ts == expected_ts, (
                f"GA {ga} point {i}: expected ts={expected_ts}, got {row.ts}"
            )
            assert row.ga == ga
            assert row.datatype == DATATYPE
            assert row.object_id == obj["id"]
            assert row.name == obj["name"]

            stored_value = row.value
            assert stored_value is not None
            expected_val = expected_by_ga[ga][i]
            assert abs(float(stored_value) - expected_val) < 1e-5, (
                f"GA {ga} point {i}: expected {expected_val}, got {stored_value}"
            )

    # Verify time span
    result = await db_session.execute(
        select(Event)
        .where(Event.house_id == house_id, Event.ga == METER_SERIES[0]["ga"])
        .order_by(Event.ts.asc())
    )
    rows = result.scalars().all()
    first_ts = rows[0].ts
    last_ts = rows[-1].ts
    span = (last_ts - first_ts).total_seconds()
    expected_span = (EXPECTED_POINTS - 1) * INTERVAL_SEC
    assert abs(span - expected_span) < 1


# Reduced dataset for MQTT full-path test (faster, broker + ingestor)
MQTT_FULLPATH_GAS = METER_SERIES[:5]  # Urms L1/L2/L3, Irms L1/L2
MQTT_FULLPATH_POINTS = 10


async def test_timeseries_via_mqtt_full_path(
    mqtt_app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Full path: publish events to MQTT topic → ingestor receives → handle_event → events table.
    Requires: running MQTT broker (localhost via SSH tunnel), MQTT_TOPIC_PREFIX=dev/
    """
    house_id = f"house-ts-mqtt-{uuid.uuid4().hex[:12]}"
    topic = f"{settings.mqtt_topic_prefix}cm/{house_id}/lm-main/v1/events"
    base_ts = 1730000000

    expected_by_ga: dict[str, list[float]] = {m["ga"]: [] for m in MQTT_FULLPATH_GAS}

    async with aiomqtt.Client(
        hostname=settings.mqtt_host,
        port=settings.mqtt_port,
        identifier="test-timeseries-publisher",
    ) as client:
        for i in range(MQTT_FULLPATH_POINTS):
            for obj in MQTT_FULLPATH_GAS:
                value = _value_for_name(obj["name"], i)
                expected_by_ga[obj["ga"]].append(value)
                payload = _make_event_payload(
                    base_ts, i,
                    ga=obj["ga"],
                    object_id=obj["id"],
                    name=obj["name"],
                    value=value,
                )
                await client.publish(topic, json.dumps(payload), qos=0)

    await asyncio.sleep(2)

    result = await db_session.execute(
        select(func.count()).select_from(Event).where(Event.house_id == house_id)
    )
    total = result.scalar_one()
    expected_total = len(MQTT_FULLPATH_GAS) * MQTT_FULLPATH_POINTS
    assert total == expected_total, (
        f"Expected {expected_total} events via MQTT, got {total}. "
        "Check MQTT broker (SSH tunnel) and MQTT_TOPIC_PREFIX=dev/"
    )

    for obj in MQTT_FULLPATH_GAS:
        ga = obj["ga"]
        result = await db_session.execute(
            select(Event)
            .where(Event.house_id == house_id, Event.ga == ga)
            .order_by(Event.ts.asc())
        )
        rows = result.scalars().all()
        assert len(rows) == MQTT_FULLPATH_POINTS, f"GA {ga}: expected {MQTT_FULLPATH_POINTS}, got {len(rows)}"
        for i, row in enumerate(rows):
            assert row.ga == ga
            assert row.datatype == DATATYPE
            expected_val = expected_by_ga[ga][i]
            assert abs(float(row.value) - expected_val) < 1e-5
