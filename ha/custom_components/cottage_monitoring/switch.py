from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .commands import ai_srv_switcher_body, auto_heating_body, projector_body
from .const import DOMAIN, HOUSE_AREA_NAME
from .entity import CottageEntity, area_name_for
from .snapshot import SwitchItem, place_device_name, slug


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]["coordinator"]
    entities: list[SwitchEntity] = [CottageAutoHeatingSwitch(coordinator)]
    plug = coordinator.data.ai_srv_switcher
    if plug is not None:
        entities.append(CottageAiSrvSwitch(coordinator, plug))
    projector = coordinator.data.projector
    if projector is not None:
        entities.append(CottageProjectorSwitch(coordinator, projector))
    async_add_entities(entities, True)


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


class _CottageNamedSwitch(CottageEntity, SwitchEntity):
    def __init__(
        self,
        coordinator,
        item: SwitchItem,
        *,
        name: str,
        helper,
        attr: str,
        icon: str,
    ) -> None:
        floors = coordinator.data.floors_by_area()
        super().__init__(
            coordinator,
            unique_id=item.unique_id,
            name=name,
            area_name=area_name_for(item.area, item.floor, floors),
        )
        self._helper = helper
        self._attr = attr
        self._attr_icon = icon
        self._device_name = place_device_name(
            raw_name=item.name,
            area=item.area,
            floor=item.floor,
            floors_by_area=floors,
        )

    def _item(self) -> SwitchItem | None:
        return getattr(self.coordinator.data, self._attr)

    def _actual_on(self) -> bool | None:
        item = self._item()
        if item is None or item.on is None:
            return None
        return bool(item.on)

    @property
    def is_on(self) -> bool:
        if self._pending_on is not None:
            return self._pending_on
        item = self._item()
        return bool(item is not None and item.on)

    async def async_turn_on(self, **kwargs) -> None:
        await self.async_call_op(self._helper, True, pending_on=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_call_op(self._helper, False, pending_on=False)


class CottageAiSrvSwitch(_CottageNamedSwitch):
    def __init__(self, coordinator, item: SwitchItem) -> None:
        super().__init__(
            coordinator,
            item,
            name="AI-SRV",
            helper=ai_srv_switcher_body,
            attr="ai_srv_switcher",
            icon="mdi:power-socket-eu",
        )
        self.entity_id = "switch.ai_srv"


class CottageProjectorSwitch(_CottageNamedSwitch):
    def __init__(self, coordinator, item: SwitchItem) -> None:
        super().__init__(
            coordinator,
            item,
            name="Проектор",
            helper=projector_body,
            attr="projector",
            icon="mdi:projector",
        )
        self.entity_id = "switch.projector"
