from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def slug(name: str) -> str:
    """Lowercase; whitespace runs become a single ``_``. Hyphens are kept (``свет_-_кухня``)."""
    return re.sub(r"\s+", "_", name.strip().lower())


def _unique_id(house_id: str, kind: str, name: str) -> str:
    return f"{house_id}:{kind}:{slug(name)}"


def _as_on(value: Any) -> bool:
    """True/1/'true' (and related) → True. None and unknown → False."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "t", "1", "on"):
            return True
        if lowered in ("false", "f", "0", "off", ""):
            return False
    return bool(value)


def _as_on_optional(value: Any) -> bool | None:
    if value is None:
        return None
    return _as_on(value)


@dataclass(frozen=True)
class LightItem:
    name: str
    on: bool
    area: str | None
    floor: str | None
    unique_id: str


@dataclass(frozen=True)
class ClimateZone:
    room: str
    area: str | None
    floor: str | None
    setpoint: float | None
    room_temp: float | None
    floor_temp: float | None
    relay_on: bool | None
    humidity: float | None
    unique_id: str


@dataclass(frozen=True)
class SensorItem:
    name: str
    kind: str  # air | floor | humidity | outdoor
    value: object
    area: str | None
    floor: str | None
    unique_id: str


@dataclass(frozen=True)
class KettleItem:
    name: str
    on: bool | None
    temp: float | None
    setpoint_c: float | None
    area: str | None
    floor: str | None
    unique_id: str
    has_setpoint: bool


@dataclass(frozen=True)
class HouseSnapshot:
    house_id: str
    online: bool
    last_seen: object
    auto_heating_enabled: bool
    lights: tuple[LightItem, ...]
    climates: tuple[ClimateZone, ...]
    sensors: tuple[SensorItem, ...]
    kettle: KettleItem | None

    @classmethod
    def from_ops(cls, house_id: str, ops: dict) -> HouseSnapshot:
        status = ops.get("get_house_status") or {}
        climate = ops.get("get_climate") or {}
        lights_op = ops.get("list_lights") or {}
        temps_op = ops.get("get_temperature") or {}
        sensors_op = ops.get("get_sensors") or {}
        kettle_op = ops.get("get_kettle") or {}

        sensors: list[SensorItem] = []
        humidity_by_area: dict[object, object] = {}

        for item in temps_op.get("items") or []:
            source = item.get("source") or "air"
            sensors.append(
                SensorItem(
                    name=item["name"],
                    kind=source,
                    value=item.get("value"),
                    area=item.get("area"),
                    floor=item.get("floor"),
                    unique_id=_unique_id(house_id, f"sensor_{source}", item["name"]),
                )
            )

        for item in sensors_op.get("items") or []:
            sensors.append(
                SensorItem(
                    name=item["name"],
                    kind="humidity",
                    value=item.get("value"),
                    area=item.get("area"),
                    floor=item.get("floor"),
                    unique_id=_unique_id(house_id, "sensor_humidity", item["name"]),
                )
            )
            humidity_by_area.setdefault(item.get("area"), item.get("value"))

        lights = tuple(
            LightItem(
                name=item["name"],
                on=_as_on(item.get("on")),
                area=item.get("area"),
                floor=item.get("floor"),
                unique_id=_unique_id(house_id, "light", item["name"]),
            )
            for item in lights_op.get("items") or []
        )

        climates = tuple(
            ClimateZone(
                room=zone["room"],
                area=zone.get("area"),
                floor=zone.get("floor"),
                setpoint=zone.get("setpoint"),
                room_temp=zone.get("room_temp"),
                floor_temp=zone.get("floor_temp"),
                relay_on=_as_on_optional(zone.get("relay_on")),
                humidity=humidity_by_area.get(zone.get("area")),
                unique_id=_unique_id(house_id, "climate", zone["room"]),
            )
            for zone in climate.get("zones") or []
        )

        appliance = kettle_op.get("appliance")
        kettle: KettleItem | None = None
        if appliance is not None:
            kettle = KettleItem(
                name=appliance["name"],
                on=_as_on_optional(appliance.get("on")),
                temp=appliance.get("temp"),
                setpoint_c=appliance.get("setpoint_c"),
                area=appliance.get("area") or "кухня",
                floor=appliance.get("floor"),
                unique_id=_unique_id(house_id, "kettle", appliance["name"]),
                has_setpoint=appliance.get("setpoint_c") is not None,
            )

        return cls(
            house_id=house_id,
            online=status.get("online_status") == "online",
            last_seen=status.get("last_seen"),
            auto_heating_enabled=_as_on(climate.get("auto_heating_enabled")),
            lights=lights,
            climates=climates,
            sensors=tuple(sensors),
            kettle=kettle,
        )
