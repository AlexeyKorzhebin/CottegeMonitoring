from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from cottage_monitoring.nord_client import NordError


def _ensure_ha_stubs() -> None:
    if "homeassistant.helpers.update_coordinator" in sys.modules:
        return

    def _mod(name: str) -> ModuleType:
        module = ModuleType(name)
        sys.modules[name] = module
        return module

    _mod("homeassistant")
    helpers = _mod("homeassistant.helpers")
    area_registry = _mod("homeassistant.helpers.area_registry")
    entity_registry = _mod("homeassistant.helpers.entity_registry")
    device_registry = _mod("homeassistant.helpers.device_registry")
    update_coordinator = _mod("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator
            self.hass = None
            self.entity_id = None
            self.written: list[tuple] = []

        async def async_added_to_hass(self):
            return None

        def _handle_coordinator_update(self):
            return None

        def async_write_ha_state(self):
            self.written.append((self._pending_on, self._pending_setpoint))

    class DeviceInfo(dict):
        pass

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    device_registry.DeviceInfo = DeviceInfo
    area_registry.async_get = lambda hass: None
    entity_registry.async_get = lambda hass: None
    helpers.area_registry = area_registry
    helpers.entity_registry = entity_registry
    helpers.device_registry = device_registry
    helpers.update_coordinator = update_coordinator


try:
    import homeassistant.helpers.update_coordinator  # noqa: F401
except ImportError:
    _ensure_ha_stubs()

from cottage_monitoring.entity import CottageEntity


class FakeClient:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc
        self.ops: list[tuple[str, dict]] = []

    async def call_op(self, name: str, body: dict | None = None) -> dict:
        self.ops.append((name, dict(body or {})))
        if self.exc:
            raise self.exc
        return {"status": "sent"}


class FakeCoordinator:
    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.data = SimpleNamespace(house_id="house", floors_by_area=lambda: {})
        self.refreshed = 0

    async def async_request_refresh(self) -> None:
        self.refreshed += 1


def test_call_op_rolls_back_pending_setpoint_on_nord_error() -> None:
    client = FakeClient(NordError(409, "{'status': 'ambiguous'}"))
    coord = FakeCoordinator(client)
    entity = CottageEntity(coord, unique_id="u", name="Полы", area_name="кухня")
    entity.hass = SimpleNamespace(async_create_task=lambda t: t.close())

    def helper(room, temp, *, ga=None):
        body = {"query": room, "setpoint_c": temp}
        if ga:
            body["ga"] = ga
        return "set_climate", body

    async def _run() -> None:
        with pytest.raises(NordError):
            await entity.async_call_op(
                helper,
                "кухня",
                24.0,
                ga="1/6/7",
                pending_setpoint=24.0,
            )

    asyncio.run(_run())
    assert entity._pending_setpoint is None
    assert entity._pending_on is None
    assert client.ops == [("set_climate", {"query": "кухня", "setpoint_c": 24.0, "ga": "1/6/7"})]
    written = getattr(entity, "written", None)
    if written is not None:
        assert written[-1] == (None, None)


def test_call_op_keeps_pending_on_success() -> None:
    client = FakeClient()
    coord = FakeCoordinator(client)
    entity = CottageEntity(coord, unique_id="u", name="Полы", area_name="кухня")
    entity.hass = SimpleNamespace(async_create_task=lambda t: t.close())

    def helper(room, temp):
        return "set_climate", {"query": room, "setpoint_c": temp}

    asyncio.run(entity.async_call_op(helper, "кухня", 22.0, pending_setpoint=22.0))
    assert entity._pending_setpoint == 22.0
