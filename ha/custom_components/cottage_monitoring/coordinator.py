from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .commands import (
    auto_heating_body,
    climate_set_temp_body,
    kettle_off_body,
    kettle_on_body,
    kettle_setpoint_body,
    lights_turn_off_body,
    lights_turn_on_body,
)
from .const import DOMAIN
from .nord_client import NordClient, NordError
from .registry import sync_floors_areas
from .snapshot import HouseSnapshot

_LOGGER = logging.getLogger(__name__)


class CottageCoordinator(DataUpdateCoordinator[HouseSnapshot]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: NordClient,
        *,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> HouseSnapshot:
        try:
            ops = {
                "get_house_status": await self.client.call_op("get_house_status"),
                "list_lights": await self.client.call_op("list_lights"),
                "get_climate": await self.client.call_op("get_climate"),
                "get_temperature": await self.client.call_op("get_temperature"),
                "get_sensors": await self.client.call_op(
                    "get_sensors", {"kind": "humidity"}
                ),
                "get_kettle": await self.client.call_op("get_kettle"),
            }
        except NordError as exc:
            raise UpdateFailed(str(exc)) from exc
        snap = HouseSnapshot.from_ops(self.client.house_id, ops)
        sync_floors_areas(self.hass, snap)
        return snap

    async def async_set_lights(self, query: str, on: bool) -> None:
        op, body = lights_turn_on_body(query) if on else lights_turn_off_body(query)
        await self.client.call_op(op, body)
        await self.async_request_refresh()

    async def async_set_climate(self, query: str, setpoint_c: float) -> None:
        op, body = climate_set_temp_body(query, setpoint_c)
        await self.client.call_op(op, body)
        await self.async_request_refresh()

    async def async_set_auto_heating(self, on: bool) -> None:
        op, body = auto_heating_body(on)
        await self.client.call_op(op, body)
        await self.async_request_refresh()

    async def async_set_kettle(self, on=None, setpoint_c=None) -> None:
        if on is None and setpoint_c is None:
            op, body = "set_kettle", {}
        elif on is None:
            op, body = kettle_setpoint_body(setpoint_c)
        elif setpoint_c is None:
            op, body = kettle_on_body() if on else kettle_off_body()
        else:
            op, body = "set_kettle", {"on": on, "setpoint_c": setpoint_c}
        await self.client.call_op(op, body)
        await self.async_request_refresh()
