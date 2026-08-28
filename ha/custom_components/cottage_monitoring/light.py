from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity

from .commands import lights_turn_off_body, lights_turn_on_body
from .const import DOMAIN
from .entity import CottageEntity, area_name_for
from .snapshot import LightItem, light_display_name, place_device_name


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    async_add_entities(
        [CottageLight(coordinator, item) for item in coordinator.data.lights],
        True,
    )


class CottageLight(CottageEntity, LightEntity):
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

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

    async def async_turn_on(self, **kwargs):
        await self.async_call_op(lights_turn_on_body, self._item_name, pending_on=True)

    async def async_turn_off(self, **kwargs):
        await self.async_call_op(lights_turn_off_body, self._item_name, pending_on=False)
