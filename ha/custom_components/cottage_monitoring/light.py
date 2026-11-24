from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity

from .commands import lights_turn_off_body, lights_turn_on_body
from .const import DOMAIN
from .entity import CottageEntity, area_name_for
from .snapshot import (
    LightItem,
    brightness_pct_to_ha,
    light_color_modes,
    light_current_color_mode,
    light_display_name,
    light_turn_on_params,
    mired_to_kelvin,
    place_device_name,
    uint32_to_rgb,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    async_add_entities(
        [CottageLight(coordinator, item) for item in coordinator.data.lights],
        True,
    )


class CottageLight(CottageEntity, LightEntity):
    def __init__(self, coordinator, item: LightItem) -> None:
        floors = coordinator.data.floors_by_area()
        super().__init__(
            coordinator,
            unique_id=item.unique_id,
            name=light_display_name(item.name),
            area_name=area_name_for(item.area, item.floor, floors),
        )
        self._device_name = place_device_name(
            raw_name=item.name,
            area=item.area,
            floor=item.floor,
            floors_by_area=floors,
        )
        self._item_name = item.name

    def _match(self) -> LightItem:
        return next(i for i in self.coordinator.data.lights if i.name == self._item_name)

    def _actual_on(self) -> bool | None:
        return self._match().on

    @property
    def is_on(self) -> bool:
        if self._pending_on is not None:
            return self._pending_on
        return self._match().on

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return {ColorMode(mode) for mode in light_color_modes(self._match())}

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode(light_current_color_mode(self._match()))

    @property
    def brightness(self) -> int | None:
        pct = self._match().brightness
        if pct is None:
            return None
        return brightness_pct_to_ha(pct)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        value = self._match().rgb
        if value is None:
            return None
        return uint32_to_rgb(value)

    @property
    def color_temp_kelvin(self) -> int | None:
        mired = self._match().color_temp
        if mired is None or mired <= 0:
            return None
        return mired_to_kelvin(mired)

    @property
    def min_color_temp_kelvin(self) -> int:
        return 2700

    @property
    def max_color_temp_kelvin(self) -> int:
        return 6500

    async def async_turn_on(self, **kwargs):
        params = light_turn_on_params(kwargs)
        await self.async_call_op(
            lights_turn_on_body,
            self._item_name,
            pending_on=True,
            **params,
        )

    async def async_turn_off(self, **kwargs):
        await self.async_call_op(lights_turn_off_body, self._item_name, pending_on=False)
