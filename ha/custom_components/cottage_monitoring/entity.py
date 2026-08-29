from __future__ import annotations

import asyncio

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, HOUSE_AREA_NAME
from .snapshot import area_name_for, place_device_name, slug

__all__ = ["CottageEntity", "area_name_for"]

# KNX status / BLE state typically lands in Nord 0.5–3 s after the control write.
_REFRESH_AFTER_WRITE_SEC = 2.5


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
        self._device_name = area_name or HOUSE_AREA_NAME
        self._pending_on: bool | None = None
        self._pending_setpoint: float | None = None

    @property
    def device_info(self) -> DeviceInfo:
        place = self._device_name or HOUSE_AREA_NAME
        house_id = self.coordinator.data.house_id
        return DeviceInfo(
            identifiers={(DOMAIN, f"{house_id}:place:{slug(place)}")},
            name=place,
            manufacturer="Cottage Monitoring",
        )

    def _actual_on(self) -> bool | None:
        return None

    def _actual_setpoint(self) -> float | None:
        return None

    def _settle_pending(self) -> None:
        actual_on = self._actual_on()
        if self._pending_on is not None and actual_on is not None and actual_on == self._pending_on:
            self._pending_on = None
        actual_sp = self._actual_setpoint()
        if self._pending_setpoint is not None and actual_sp is not None:
            if abs(float(actual_sp) - float(self._pending_setpoint)) <= 0.05:
                self._pending_setpoint = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._reassign_area()

    def _handle_coordinator_update(self) -> None:
        self._settle_pending()
        area = self._ha_area_from_snap()
        if area:
            self._area_name = area
            self._device_name = area
        self._reassign_area()
        super()._handle_coordinator_update()

    def _ha_area_from_snap(self) -> str | None:
        snap = self.coordinator.data
        if snap is None:
            return self._area_name
        floors = snap.floors_by_area()
        uid = self._attr_unique_id
        for item in (*snap.lights, *snap.climates, *snap.sensors):
            if item.unique_id == uid:
                raw = getattr(item, "name", None) or getattr(item, "room", None) or ""
                return place_device_name(
                    raw_name=raw,
                    area=item.area,
                    floor=item.floor,
                    floors_by_area=floors,
                )
        if snap.kettle is not None and snap.kettle.unique_id == uid:
            return place_device_name(
                raw_name=snap.kettle.name,
                area=snap.kettle.area,
                floor=snap.kettle.floor,
                floors_by_area=floors,
            )
        return self._area_name or self._device_name

    def _reassign_area(self) -> None:
        if self.hass is None or not self.entity_id:
            return
        name = self._ha_area_from_snap()
        ents = er.async_get(self.hass)
        entry = ents.async_get(self.entity_id)
        area_id = None
        if name:
            areas = ar.async_get(self.hass)
            area = next((a for a in areas.async_list_areas() if a.name == name), None)
            if area is not None:
                area_id = area.id
        label = self._attr_name
        if (
            entry is not None
            and entry.original_name == label
            and entry.has_entity_name
            and (area_id is None or entry.area_id == area_id)
        ):
            return
        kwargs: dict = {"original_name": label, "has_entity_name": True}
        if area_id is not None:
            kwargs["area_id"] = area_id
        ents.async_update_entity(self.entity_id, **kwargs)

    async def async_call_op(
        self,
        helper,
        *args,
        pending_on: bool | None = None,
        pending_setpoint: float | None = None,
    ) -> None:
        if pending_on is not None:
            self._pending_on = pending_on
        if pending_setpoint is not None:
            self._pending_setpoint = pending_setpoint
        if pending_on is not None or pending_setpoint is not None:
            self.async_write_ha_state()
        op, body = helper(*args)
        await self.coordinator.client.call_op(op, body)

        async def _later() -> None:
            await asyncio.sleep(_REFRESH_AFTER_WRITE_SEC)
            await self.coordinator.async_request_refresh()

        self.hass.async_create_task(_later())
