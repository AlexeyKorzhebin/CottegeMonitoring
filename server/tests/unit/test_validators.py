"""Unit tests for validators: _should_be_timeseries, CommandCreate."""

from __future__ import annotations

import pytest

from cottage_monitoring.schemas.command import CommandCreate
from cottage_monitoring.services.schema_service import _should_be_timeseries


def test_temp_tag_is_timeseries() -> None:
    """tags with temp → True."""
    obj = {"tags": "heat, temp", "datatype": 9001}
    assert _should_be_timeseries(obj) is True


def test_meter_tag_is_timeseries() -> None:
    """tags with meter → True."""
    obj = {"tags": "meter", "datatype": 14}
    assert _should_be_timeseries(obj) is True


def test_humidity_tag_is_timeseries() -> None:
    """tags with humidity → True."""
    obj = {"tags": "humidity", "datatype": 5}
    assert _should_be_timeseries(obj) is True


def test_control_bool_not_timeseries() -> None:
    """control + light, bool datatype → False."""
    obj = {"tags": "control, light", "datatype": 1001}
    assert _should_be_timeseries(obj) is False


def test_numeric_without_control_is_timeseries() -> None:
    """numeric + no control tag → True."""
    obj = {"tags": "status", "datatype": 9001}
    assert _should_be_timeseries(obj) is True


def test_numeric_with_control_not_timeseries() -> None:
    """numeric but has control tag → False."""
    obj = {"tags": "control", "datatype": 14}
    assert _should_be_timeseries(obj) is False


def test_units_celsius_is_timeseries() -> None:
    """units °C → True."""
    obj = {"tags": "", "datatype": 7, "units": "°C"}
    assert _should_be_timeseries(obj) is True


def test_units_kwh_is_timeseries() -> None:
    """units kWh → True."""
    obj = {"tags": "", "datatype": 7, "units": "kWh"}
    assert _should_be_timeseries(obj) is True


def test_bool_no_special_tags() -> None:
    """bool, no timeseries tags → False."""
    obj = {"tags": "status, light", "datatype": 1001}
    assert _should_be_timeseries(obj) is False


def test_string_type_not_timeseries() -> None:
    """datatype 255 (string) → False."""
    obj = {"tags": "monitoring", "datatype": 255}
    assert _should_be_timeseries(obj) is False


def test_command_create_single() -> None:
    """CommandCreate(ga=..., value=...) → valid."""
    cmd = CommandCreate(ga="1/1/1", value=True)
    assert cmd.ga == "1/1/1"
    assert cmd.value is True
    assert cmd.items is None


def test_command_create_batch() -> None:
    """CommandCreate(items=[...]) → valid."""
    cmd = CommandCreate(items=[{"ga": "1/1/1", "value": True}])
    assert cmd.items is not None
    assert len(cmd.items) == 1
    assert cmd.items[0].ga == "1/1/1"
    assert cmd.items[0].value is True


def test_command_create_no_ga_no_items_raises() -> None:
    """CommandCreate() without ga+value or items → raises ValueError."""
    with pytest.raises(ValueError, match="Either"):
        CommandCreate()
