from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from .const import DOMAIN
from .entity import CottageEntity, area_name_for
from .snapshot import SensorItem


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    async_add_entities(
        [CottageSensor(coordinator, item) for item in coordinator.data.sensors],
        True,
    )


class CottageSensor(CottageEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, item: SensorItem) -> None:
        super().__init__(
            coordinator,
            unique_id=item.unique_id,
            name=item.name,
            area_name=area_name_for(item.area, item.floor),
        )
        self._item_name = item.name
        if item.kind == "humidity":
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        else:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def _match(self) -> SensorItem:
        return next(s for s in self.coordinator.data.sensors if s.name == self._item_name)

    @property
    def native_value(self):
        return self._match().value
