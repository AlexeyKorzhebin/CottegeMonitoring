from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from .const import FLOOR_LABELS, HOUSE_AREA_NAME

ENERGY_HA_BY_GA: dict[str, str] = {
    "32/1/35": "power",
    "32/1/7": "frequency",
    "32/1/59": "meter",
    "32/1/57": "hour",
    "32/1/58": "daily",
    "32/1/38": "pf",
}

ENERGY_DISPLAY_NAME: dict[str, str] = {
    "power": "Сейчас",
    "frequency": "Частота",
    "meter": "Счётчик",
    "hour": "За час",
    "daily": "За сутки",
    "pf": "PF",
}


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


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ".").strip())
        except ValueError:
            return None
    return None


def _floor_label(name: str) -> str:
    """«Темп  - холл 1 этаж» и «холл 1 этаж» → одно и то же."""
    text = re.sub(r"\s+", " ", (name or "").strip().lower())
    return re.sub(r"^темп\s*-+\s*", "", text).strip()


def climate_shown_temperature(
    *, floor_temp: float | None, room_temp: float | None
) -> float | None:
    """Число на карточке «Полы» в режиме Климат: пол, если датчик зоны есть."""
    if floor_temp is not None:
        return floor_temp
    return room_temp


def pick_area_entity(
    current: str | None,
    desired: str | None,
    *,
    current_is_ours: bool,
) -> tuple[bool, str | None]:
    """Назначать воздух/влажность зоны, не затирая чужой ручной выбор."""
    if current == desired:
        return False, current
    if current is None or current_is_ours:
        return True, desired
    return False, current


def _reading_by_place(
    sensors: tuple[SensorItem, ...] | list[SensorItem],
    kind: str,
    floors_by_area: dict[str, frozenset[str]],
) -> dict[str, list[SensorItem]]:
    grouped: dict[str, list[SensorItem]] = {}
    for sensor in sensors:
        if sensor.kind != kind:
            continue
        place = place_device_name(
            raw_name=sensor.name,
            area=sensor.area,
            floor=sensor.floor,
            floors_by_area=floors_by_area,
        )
        grouped.setdefault(place, []).append(sensor)
    return grouped


def _single_reading(
    grouped: dict[str, list[SensorItem]], place: str
) -> float | None:
    items = grouped.get(place) or []
    if len(items) != 1:
        return None
    return _as_float(items[0].value)


def match_zone_floor_temp(
    *,
    room: str,
    area: str | None,
    floor: str | None,
    floor_sensors: list[SensorItem],
    floors_by_area: dict[str, frozenset[str]],
    fallback: Any,
) -> float | None:
    """Датчик пола этой зоны. Резолвер get_climate путает соседние комнаты."""
    label = _floor_label(room)
    named = [sensor for sensor in floor_sensors if _floor_label(sensor.name) == label]
    if len(named) == 1:
        return _as_float(named[0].value)
    place = place_device_name(
        raw_name=room,
        area=area,
        floor=floor,
        floors_by_area=floors_by_area,
    )
    same_place = [
        sensor
        for sensor in floor_sensors
        if place_device_name(
            raw_name=sensor.name,
            area=sensor.area,
            floor=sensor.floor,
            floors_by_area=floors_by_area,
        )
        == place
    ]
    if len(same_place) == 1:
        return _as_float(same_place[0].value)
    return _as_float(fallback)


def floors_by_area_from_items(
    *groups: tuple,
) -> dict[str, frozenset[str]]:
    d: dict[str, set[str]] = {}
    for group in groups:
        for item in group:
            area = getattr(item, "area", None)
            floor = getattr(item, "floor", None)
            if area and floor:
                d.setdefault(area, set()).add(floor)
    return {k: frozenset(v) for k, v in d.items()}


def area_name_for(
    area: str | None,
    floor: str | None,
    floors_by_area: dict[str, frozenset[str]] | None = None,
) -> str | None:
    """HA Area names are unique. Same Nord area on two floors → «холл (1 этаж)»."""
    if floor == "outside":
        return area or FLOOR_LABELS["outside"]
    if (
        area
        and floor
        and floors_by_area
        and len(floors_by_area.get(area, frozenset())) > 1
    ):
        label = FLOOR_LABELS.get(floor)
        if label:
            return f"{area} ({label})"
    return area


_SPLIT_AREA_RE = re.compile(r"^(.+) \([12] этаж\)$")


def leftover_split_area_names(
    existing_names: set[str],
    floors_by_area: dict[str, frozenset[str]],
) -> list[str]:
    """«спальня (1 этаж)» leftovers after that Nord area lives on only one floor."""
    out: list[str] = []
    for name in existing_names:
        m = _SPLIT_AREA_RE.fullmatch(name)
        if not m:
            continue
        base = m.group(1)
        if len(floors_by_area.get(base, frozenset())) <= 1:
            out.append(name)
    return sorted(out)


def _zone_index(surface: str) -> str | None:
    """«гостиная 1» → «1». Ignore «холл 1 этаж»."""
    text = (surface or "").strip()
    if "этаж" in text.lower():
        return None
    m = re.search(r"\s([12])\s*$", text)
    return m.group(1) if m else None


def sensor_ha_profile(kind: str) -> dict[str, str | None]:
    profiles = {
        "power": {"device_class": "power", "unit": "W", "state_class": "measurement"},
        "frequency": {"device_class": "frequency", "unit": "Hz", "state_class": "measurement"},
        "meter": {"device_class": "energy", "unit": "kWh", "state_class": "total_increasing"},
        "hour": {"device_class": "energy", "unit": "kWh", "state_class": "total"},
        "daily": {"device_class": "energy", "unit": "kWh", "state_class": "total"},
        "pf": {"device_class": "power_factor", "unit": None, "state_class": "measurement"},
        "battery": {"device_class": "battery", "unit": "%", "state_class": "measurement"},
        "humidity": {"device_class": "humidity", "unit": "%", "state_class": "measurement"},
        "air": {"device_class": "temperature", "unit": "°C", "state_class": "measurement"},
        "floor": {"device_class": "temperature", "unit": "°C", "state_class": "measurement"},
    }
    return profiles.get(kind, {"device_class": "temperature", "unit": "°C", "state_class": "measurement"})


def sensor_display_name(*, name: str, kind: str) -> str:
    """Short labels for HA cards. Room lives on the area/device, not the entity."""
    raw = (name or "").strip()
    if kind == "battery":
        return "Батарея"
    if kind in ENERGY_DISPLAY_NAME:
        return ENERGY_DISPLAY_NAME[kind]
    if kind == "humidity":
        return "Влажность"
    if kind == "air":
        return "Воздух"
    if kind == "floor":
        idx = _zone_index(re.sub(r"^темп\s*-+\s*", "", raw, flags=re.I))
        return f"Пол {idx}" if idx else "Пол"
    if kind == "outdoor":
        return _weather_display_name(raw)
    return raw or "Датчик"


def _weather_display_name(name: str) -> str:
    n = name.lower()
    pairs = (
        ("ощущение", "Ощущается"),
        ("направление", "Направление"),
        ("порывы", "Порывы"),
        ("скорость", "Ветер"),
        ("влажность", "Влажность"),
        ("давление", "Давление"),
        ("описание", "Погода"),
        ("температура", "Температура"),
    )
    for needle, label in pairs:
        if needle in n:
            return label
    stripped = re.sub(r"^погода\s*-+\s*", "", name, flags=re.I).strip()
    return stripped[:1].upper() + stripped[1:] if stripped else "Погода"


def light_display_name(name: str) -> str:
    low = (name or "").lower()
    if "тайфайтер" in low:
        return "Тайфайтер"
    if "торшер" in low:
        return "Торшер"
    if "подсветка" in low:
        return "Подсветка"
    return "Свет"


def climate_display_name(room: str) -> str:
    idx = _zone_index(room or "")
    return f"Полы {idx}" if idx else "Полы"


def heat_display_name(room: str) -> str:
    idx = _zone_index(room or "")
    return f"Нагрев {idx}" if idx else "Нагрев"


_UNPLACED_HINTS: tuple[tuple[str, str], ...] = (
    ("серверн", "серверная"),
    ("server_room", "серверная"),
    ("бытов", "бытовка"),
    ("чердак", "чердак"),
)


def place_device_name(
    *,
    raw_name: str,
    area: str | None,
    floor: str | None,
    floors_by_area: dict[str, frozenset[str]] | None = None,
) -> str:
    """HA device name = room. Entity name stays short (Воздух, Свет, …)."""
    named = area_name_for(area, floor, floors_by_area)
    if named:
        return named
    if floor == "outside":
        return FLOOR_LABELS["outside"]
    low = (raw_name or "").lower()
    for needle, label in _UNPLACED_HINTS:
        if needle in low:
            return label
    return HOUSE_AREA_NAME


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
    kind: str  # air | floor | humidity | outdoor | battery | power | frequency | meter | hour | daily | pf
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

        battery_op = ops.get("get_sensors_battery") or {}
        energy_op = ops.get("get_energy_status") or {}
        for item in battery_op.get("items") or []:
            sensors.append(
                SensorItem(
                    name=item["name"],
                    kind="battery",
                    value=item.get("value"),
                    area=item.get("area"),
                    floor=item.get("floor"),
                    unique_id=_unique_id(house_id, "sensor_battery", item["name"]),
                )
            )
        for item in energy_op.get("items") or []:
            ga = item.get("ga")
            key = ENERGY_HA_BY_GA.get(ga)
            if not key:
                continue
            sensors.append(
                SensorItem(
                    name=ENERGY_DISPLAY_NAME[key],
                    kind=key,
                    value=item.get("value"),
                    area=None,
                    floor=None,
                    unique_id=_unique_id(house_id, "energy", key),
                )
            )

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

        zone_rows = climate.get("zones") or []
        floors = floors_by_area_from_items(
            lights,
            sensors,
            [
                SimpleNamespace(area=zone.get("area"), floor=zone.get("floor"))
                for zone in zone_rows
            ],
        )
        air_by_place = _reading_by_place(sensors, "air", floors)
        humidity_by_place = _reading_by_place(sensors, "humidity", floors)
        floor_sensors = [sensor for sensor in sensors if sensor.kind == "floor"]

        climates_list: list[ClimateZone] = []
        for zone in zone_rows:
            place = place_device_name(
                raw_name=zone["room"],
                area=zone.get("area"),
                floor=zone.get("floor"),
                floors_by_area=floors,
            )
            room_temp = _as_float(zone.get("room_temp"))
            if room_temp is None:
                room_temp = _single_reading(air_by_place, place)
            climates_list.append(
                ClimateZone(
                    room=zone["room"],
                    area=zone.get("area"),
                    floor=zone.get("floor"),
                    setpoint=_as_float(zone.get("setpoint")),
                    room_temp=room_temp,
                    floor_temp=match_zone_floor_temp(
                        room=zone["room"],
                        area=zone.get("area"),
                        floor=zone.get("floor"),
                        floor_sensors=floor_sensors,
                        floors_by_area=floors,
                        fallback=zone.get("floor_temp"),
                    ),
                    relay_on=_as_on_optional(zone.get("relay_on")),
                    humidity=_single_reading(humidity_by_place, place),
                    unique_id=_unique_id(house_id, "climate", zone["room"]),
                )
            )
        climates = tuple(climates_list)

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

    def area_climate_sensor_uids(self) -> dict[str, dict[str, str | None]]:
        """Комнаты с уставкой пола → unique_id воздуха и влажности для режима Климат."""
        floors = self.floors_by_area()
        places: set[str] = set()
        for zone in self.climates:
            places.add(
                place_device_name(
                    raw_name=zone.room,
                    area=zone.area,
                    floor=zone.floor,
                    floors_by_area=floors,
                )
            )
        air = _reading_by_place(self.sensors, "air", floors)
        humidity = _reading_by_place(self.sensors, "humidity", floors)
        out: dict[str, dict[str, str | None]] = {}
        for place in sorted(places):
            airs = air.get(place) or []
            hums = humidity.get(place) or []
            out[place] = {
                "air": airs[0].unique_id if len(airs) == 1 else None,
                "humidity": hums[0].unique_id if len(hums) == 1 else None,
            }
        return out

    def floors_by_area(self) -> dict[str, frozenset[str]]:
        groups: list[tuple] = [self.lights, self.climates, self.sensors]
        if self.kettle is not None:
            groups.append((self.kettle,))
        return floors_by_area_from_items(*groups)
