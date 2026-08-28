from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import DOMAIN, HOUSE_AREA_NAME
from .entity import CottageEntity, area_name_for
from .snapshot import ClimateZone, heat_display_name, place_device_name, slug


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    entities = [CottageHouseOnline(coordinator)]
    entities.extend(
        CottageZoneHeat(coordinator, zone) for zone in coordinator.data.climates
    )
    async_add_entities(entities, True)


class CottageHouseOnline(CottageEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator) -> None:
        super().__init__(
            coordinator,
            unique_id=f"{coordinator.data.house_id}:house_online:{slug(HOUSE_AREA_NAME)}",
            name="Онлайн",
            area_name=HOUSE_AREA_NAME,
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.online

    @property
    def extra_state_attributes(self) -> dict:
        return {"last_seen": self.coordinator.data.last_seen}


class CottageZoneHeat(CottageEntity, BinarySensorEntity):
    def __init__(self, coordinator, zone: ClimateZone) -> None:
        floors = coordinator.data.floors_by_area()
        super().__init__(
            coordinator,
            unique_id=f"{coordinator.data.house_id}:relay:{slug(zone.room)}",
            name=heat_display_name(zone.room),
            area_name=area_name_for(zone.area, zone.floor, floors),
        )
        self._device_name = place_device_name(
            raw_name=zone.room,
            area=zone.area,
            floor=zone.floor,
            floors_by_area=floors,
        )
        self._room = zone.room

    def _zone(self) -> ClimateZone:
        return next(z for z in self.coordinator.data.climates if z.room == self._room)

    @property
    def is_on(self) -> bool:
        return bool(self._zone().relay_on)
