from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)

from .const import DOMAIN
from .entity import CottageEntity, area_name_for
from .snapshot import SensorItem, place_device_name, sensor_display_name


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    async_add_entities(
        [CottageSensor(coordinator, item) for item in coordinator.data.sensors],
        True,
    )


class CottageSensor(CottageEntity, SensorEntity):
    def __init__(self, coordinator, item: SensorItem) -> None:
        floors = coordinator.data.floors_by_area()
        label = sensor_display_name(name=item.name, kind=item.kind)
        super().__init__(
            coordinator,
            unique_id=item.unique_id,
            name=label,
            area_name=area_name_for(item.area, item.floor, floors),
        )
        self._item_name = item.name
        self._device_name = place_device_name(
            raw_name=item.name,
            area=item.area,
            floor=item.floor,
            floors_by_area=floors,
        )
        self._apply_device_class(item.kind, label)

    def _apply_device_class(self, kind: str, label: str) -> None:
        if kind == "humidity" or (kind == "outdoor" and label == "Влажность"):
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            return
        if kind == "outdoor" and label == "Давление":
            self._attr_device_class = SensorDeviceClass.ATMOSPHERIC_PRESSURE
            self._attr_native_unit_of_measurement = UnitOfPressure.MMHG
            self._attr_state_class = SensorStateClass.MEASUREMENT
            return
        if kind == "outdoor" and label in ("Ветер", "Порывы"):
            self._attr_device_class = SensorDeviceClass.WIND_SPEED
            self._attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND
            self._attr_state_class = SensorStateClass.MEASUREMENT
            return
        if kind == "outdoor" and label in ("Погода", "Направление"):
            self._attr_device_class = None
            self._attr_native_unit_of_measurement = None
            self._attr_state_class = None
            return
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    def _match(self) -> SensorItem:
        return next(s for s in self.coordinator.data.sensors if s.name == self._item_name)

    @property
    def native_value(self):
        val = self._match().value
        if self._attr_state_class is None:
            return val
        if isinstance(val, bool) or val is None:
            return None if val is None else val
        if isinstance(val, (int, float)):
            return val
        if isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return None
        return val
