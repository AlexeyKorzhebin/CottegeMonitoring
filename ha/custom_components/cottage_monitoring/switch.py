from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .commands import auto_heating_body
from .const import DOMAIN, HOUSE_AREA_NAME
from .entity import CottageEntity
from .snapshot import slug


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    async_add_entities([CottageAutoHeatingSwitch(coordinator)], True)


class CottageAutoHeatingSwitch(CottageEntity, SwitchEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(
            coordinator,
            unique_id=f"{coordinator.data.house_id}:auto_heating:{slug(HOUSE_AREA_NAME)}",
            name="Автополы",
            area_name=HOUSE_AREA_NAME,
        )

    def _actual_on(self) -> bool | None:
        return self.coordinator.data.auto_heating_enabled

    @property
    def is_on(self) -> bool:
        if self._pending_on is not None:
            return self._pending_on
        return self.coordinator.data.auto_heating_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.async_call_op(auto_heating_body, True, pending_on=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_call_op(auto_heating_body, False, pending_on=False)
