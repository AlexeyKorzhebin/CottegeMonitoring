from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, FLOOR_LABELS


def area_name_for(area: str | None, floor: str | None) -> str | None:
    if floor == "outside":
        return FLOOR_LABELS["outside"]
    return area


class CottageEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        *,
        unique_id: str,
        name: str,
        area_name: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._area_name = area_name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data.house_id)},
            name="Cottage",
            manufacturer="Cottage Monitoring",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self._area_name:
            return
        areas = ar.async_get(self.hass)
        area = next((a for a in areas.async_list_areas() if a.name == self._area_name), None)
        if area is None:
            return
        er.async_get(self.hass).async_update_entity(self.entity_id, area_id=area.id)

    async def async_call_op(self, helper, *args) -> None:
        op, body = helper(*args)
        await self.coordinator.client.call_op(op, body)
        await self.coordinator.async_request_refresh()
