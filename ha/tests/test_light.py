from __future__ import annotations

import asyncio
import sys
from enum import StrEnum
from types import ModuleType, SimpleNamespace

from cottage_monitoring.snapshot import LightItem


def _ensure_ha_stubs() -> None:
    if "homeassistant.components.light" in sys.modules:
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
    components = _mod("homeassistant.components")
    light_mod = _mod("homeassistant.components.light")

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator
            self.hass = None
            self.entity_id = None

        async def async_added_to_hass(self):
            return None

        def _handle_coordinator_update(self):
            return None

        def async_write_ha_state(self):
            return None

    class DeviceInfo(dict):
        pass

    class ColorMode(StrEnum):
        ONOFF = "onoff"
        BRIGHTNESS = "brightness"
        COLOR_TEMP = "color_temp"
        RGB = "rgb"

    class LightEntity:
        pass

    light_mod.ColorMode = ColorMode
    light_mod.LightEntity = LightEntity
    light_mod.ATTR_BRIGHTNESS = "brightness"
    light_mod.ATTR_COLOR_TEMP = "color_temp"
    light_mod.ATTR_COLOR_TEMP_KELVIN = "color_temp_kelvin"
    light_mod.ATTR_RGB_COLOR = "rgb_color"
    update_coordinator.CoordinatorEntity = CoordinatorEntity
    device_registry.DeviceInfo = DeviceInfo
    area_registry.async_get = lambda hass: None
    entity_registry.async_get = lambda hass: None
    helpers.area_registry = area_registry
    helpers.entity_registry = entity_registry
    helpers.device_registry = device_registry
    helpers.update_coordinator = update_coordinator
    components.light = light_mod


try:
    import homeassistant.components.light  # noqa: F401
except ImportError:
    _ensure_ha_stubs()

from homeassistant.components.light import ColorMode

from cottage_monitoring.light import CottageLight


class FakeClient:
    def __init__(self) -> None:
        self.ops: list[tuple[str, dict]] = []

    async def call_op(self, name: str, body: dict | None = None) -> dict:
        self.ops.append((name, dict(body or {})))
        return {"status": "sent"}


class FakeCoordinator:
    def __init__(self, lights: tuple[LightItem, ...]) -> None:
        self.client = FakeClient()
        self.data = SimpleNamespace(
            house_id="house",
            lights=lights,
            floors_by_area=lambda: {},
        )
        self.refreshed = 0

    async def async_request_refresh(self) -> None:
        self.refreshed += 1


def _kitchen() -> LightItem:
    return LightItem(
        name="Свет - кухня",
        on=True,
        area="кухня",
        floor="1",
        unique_id="house:light:кухня",
    )


def _tima() -> LightItem:
    return LightItem(
        name="Свет - спальня Тима",
        on=True,
        area="Тимнина комната",
        floor="2",
        unique_id="house:light:тима",
        brightness=40,
        color_temp=300,
        rgb=16711680,
        supports_brightness=True,
        supports_color_temp=True,
        supports_rgb=True,
    )


def test_onoff_light_stays_onoff_color_mode() -> None:
    light = CottageLight(FakeCoordinator((_kitchen(),)), _kitchen())
    assert light.supported_color_modes == {ColorMode.ONOFF}
    assert light.color_mode == ColorMode.ONOFF
    assert light.brightness is None
    assert light.rgb_color is None
    assert light.color_temp_kelvin is None


def test_ceiling_light_exposes_color_temp_and_rgb() -> None:
    light = CottageLight(FakeCoordinator((_tima(),)), _tima())
    assert light.supported_color_modes == {ColorMode.COLOR_TEMP, ColorMode.RGB}
    assert ColorMode.ONOFF not in light.supported_color_modes
    assert ColorMode.BRIGHTNESS not in light.supported_color_modes
    assert light.color_mode == ColorMode.RGB
    assert light.brightness == 102
    assert light.rgb_color == (255, 0, 0)
    assert light.color_temp_kelvin == 3333


def test_async_turn_on_without_params_sends_on_true() -> None:
    coord = FakeCoordinator((_kitchen(),))
    light = CottageLight(coord, _kitchen())
    light.hass = SimpleNamespace(async_create_task=lambda t: t.close())

    asyncio.run(light.async_turn_on())
    assert coord.client.ops == [
        ("set_lights", {"query": "Свет - кухня", "on": True, "skip_unchanged": False})
    ]


def test_async_turn_on_with_params_omits_on_and_converts_units() -> None:
    coord = FakeCoordinator((_tima(),))
    light = CottageLight(coord, _tima())
    light.hass = SimpleNamespace(async_create_task=lambda t: t.close())

    asyncio.run(
        light.async_turn_on(
            brightness=255,
            color_temp_kelvin=4000,
            rgb_color=(17, 34, 51),
        )
    )
    assert len(coord.client.ops) == 1
    name, body = coord.client.ops[0]
    assert name == "set_lights"
    assert body["query"] == "Свет - спальня Тима"
    assert body["skip_unchanged"] is False
    assert "on" not in body
    assert body["brightness"] == 100
    assert body["rgb"] == 0x112233
    assert body["color_temp"] == 250


def test_async_turn_off_writes_on_false_only() -> None:
    coord = FakeCoordinator((_tima(),))
    light = CottageLight(coord, _tima())
    light.hass = SimpleNamespace(async_create_task=lambda t: t.close())

    asyncio.run(light.async_turn_off())
    assert coord.client.ops == [
        (
            "set_lights",
            {"query": "Свет - спальня Тима", "on": False, "skip_unchanged": False},
        )
    ]
