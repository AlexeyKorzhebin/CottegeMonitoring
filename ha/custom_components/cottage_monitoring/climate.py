from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .commands import climate_set_temp_body
from .const import DOMAIN
from .entity import CottageEntity
from .snapshot import ClimateZone


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    async_add_entities(
        [CottageClimate(coordinator, zone) for zone in coordinator.data.climates],
        True,
    )


class CottageClimate(CottageEntity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, zone: ClimateZone) -> None:
        super().__init__(
            coordinator,
            unique_id=zone.unique_id,
            name=zone.room,
            area_name=zone.area,
        )
        self._room = zone.room

    def _zone(self) -> ClimateZone:
        return next(z for z in self.coordinator.data.climates if z.room == self._room)

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT

    @property
    def current_temperature(self) -> float | None:
        return self._zone().room_temp

    @property
    def target_temperature(self) -> float | None:
        return self._zone().setpoint

    @property
    def current_humidity(self) -> float | None:
        return self._zone().humidity

    @property
    def hvac_action(self) -> HVACAction:
        return HVACAction.HEATING if self._zone().relay_on else HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        return

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self.async_call_op(climate_set_temp_body, self._room, float(temp))
