from __future__ import annotations

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, STATE_ON, UnitOfTemperature

from .commands import kettle_off_body, kettle_on_body, kettle_setpoint_body
from .const import DOMAIN
from .entity import CottageEntity
from .snapshot import KettleItem


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    kettle = coordinator.data.kettle
    if kettle is None:
        return
    async_add_entities([CottageKettle(coordinator, kettle)], True)


class CottageKettle(CottageEntity, WaterHeaterEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = [STATE_ON, STATE_OFF]
    _attr_min_temp = 40
    _attr_max_temp = 100

    def __init__(self, coordinator, item: KettleItem) -> None:
        super().__init__(
            coordinator,
            unique_id=item.unique_id,
            name=item.name,
            area_name=item.area,
        )

    def _item(self) -> KettleItem | None:
        return self.coordinator.data.kettle

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        item = self._item()
        if item is not None and item.has_setpoint:
            return (
                WaterHeaterEntityFeature.ON_OFF
                | WaterHeaterEntityFeature.TARGET_TEMPERATURE
            )
        return WaterHeaterEntityFeature.ON_OFF

    @property
    def current_temperature(self) -> float | None:
        item = self._item()
        return None if item is None else item.temp

    @property
    def target_temperature(self) -> float | None:
        item = self._item()
        if item is None or not item.has_setpoint:
            return None
        return item.setpoint_c

    @property
    def current_operation(self) -> str:
        item = self._item()
        if item is not None and item.on:
            return STATE_ON
        return STATE_OFF

    @property
    def is_on(self) -> bool:
        item = self._item()
        return bool(item is not None and item.on)

    async def async_turn_on(self, **kwargs) -> None:
        await self.async_call_op(kettle_on_body)

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_call_op(kettle_off_body)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        if operation_mode == STATE_ON:
            await self.async_turn_on()
        else:
            await self.async_turn_off()

    async def async_set_temperature(self, **kwargs) -> None:
        item = self._item()
        if item is None or not item.has_setpoint:
            return
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self.async_call_op(kettle_setpoint_body, float(temp))
