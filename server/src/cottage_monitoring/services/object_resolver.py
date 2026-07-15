"""Semantic object resolution by tags, names, and GA families."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.models.object import Object

if TYPE_CHECKING:
    from pymorphy3 import MorphAnalyzer

ResolveStatus = Literal["ok", "not_found", "ambiguous"]

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+")

# Tokens that appear in almost every query/name and must not drive matching.
_STOP_LEMMAS = frozenset(
    {
        "свет",
        "освещение",
        "статус",
        "температура",
        "темп",
        "датчик",
        "значение",
        "комната",
        "этаж",
        "уставка",
        "контроль",
        "control",
        "light",
        "status",
        "temp",
        "sensor",
        "floor",
        "heat",
        "setpoint",
    }
)

# Map surface / lemma forms to the tokens used in object names/tags.
_SYNONYMS = {
    "зал": "гостиная",
    "гостиная": "гостиная",
    "настя": "настин",
    "наст": "настин",  # pymorphy sometimes yields this for «Насте»
    "настина": "настин",
    "тим": "тимин",
}


class ObjectRole(StrEnum):
    LIGHT_CONTROL = "light_control"
    LIGHT_STATUS = "light_status"
    FLOOR_TEMP = "floor_temp"
    ROOM_TEMP = "room_temp"
    ROOM_HUMIDITY = "room_humidity"
    CLIMATE_SETPOINT = "climate_setpoint"
    HEAT_RELAY_CONTROL = "heat_relay_control"
    HEAT_RELAY_STATUS = "heat_relay_status"
    AUTO_HEATING = "auto_heating"
    ENERGY = "energy"
    HEATING_DIAG = "heating_diag"
    WEATHER = "weather"
    ZIGBEE_APPLIANCE = "zigbee_appliance"
    SENSOR = "sensor"
    OTHER = "other"


class DiscoverKind(StrEnum):
    LIGHT = "light"
    TEMP = "temp"
    CLIMATE = "climate"
    SENSOR = "sensor"
    ENERGY = "energy"
    HEATING = "heating"
    APPLIANCE = "appliance"
    ALL = "all"


@dataclass(frozen=True)
class ResolvedObject:
    ga: str
    name: str
    tags: list[str]
    role: ObjectRole
    datatype: int


@dataclass
class ResolveResult:
    status: ResolveStatus
    matches: list[ResolvedObject]

    @property
    def single(self) -> ResolvedObject | None:
        if self.status == "ok" and len(self.matches) == 1:
            return self.matches[0]
        return None


def _tag_list(tags: str) -> list[str]:
    return [t.strip().lower() for t in (tags or "").split(",") if t.strip()]


def _has_all(tagset: set[str], *required: str) -> bool:
    return all(r in tagset for r in required)


def classify_object(obj: Object) -> ObjectRole:
    tagset = set(_tag_list(obj.tags))
    name = (obj.name or "").lower()
    ga = obj.ga

    if ga == "1/7/1" or _has_all(tagset, "auto", "heat"):
        return ObjectRole.AUTO_HEATING
    if ga.startswith("34/1/") and "monitoring" in tagset:
        return ObjectRole.HEATING_DIAG
    if _has_all(tagset, "control", "light"):
        return ObjectRole.LIGHT_CONTROL
    if _has_all(tagset, "status", "light") and "control" not in tagset:
        return ObjectRole.LIGHT_STATUS
    if _has_all(tagset, "setpoint", "heat"):
        return ObjectRole.CLIMATE_SETPOINT
    if _has_all(tagset, "control", "heat"):
        return ObjectRole.HEAT_RELAY_CONTROL
    if _has_all(tagset, "status", "heat") and "control" not in tagset:
        return ObjectRole.HEAT_RELAY_STATUS
    if ga.startswith("1/3/") and _has_all(tagset, "temp", "heat") and "setpoint" not in tagset:
        return ObjectRole.FLOOR_TEMP
    if "temperature" in tagset and "zb_sensor" in tagset:
        return ObjectRole.ROOM_TEMP
    if "humidity" in tagset and "zb_sensor" in tagset:
        return ObjectRole.ROOM_HUMIDITY
    if "weather" in tagset:
        return ObjectRole.WEATHER
    if "meter" in tagset:
        return ObjectRole.ENERGY
    if "teapot" in tagset or "чайник" in name or "kettle" in name or "teapot" in name:
        return ObjectRole.ZIGBEE_APPLIANCE
    if _has_all(tagset, "zigbee", "zigbee_send") or "ble" in tagset:
        if "zigbee_send" in tagset or "control" in tagset:
            return ObjectRole.ZIGBEE_APPLIANCE
    if tagset & {"temp", "humidity", "meter", "occupancy", "illuminance", "battery"}:
        return ObjectRole.SENSOR
    return ObjectRole.OTHER


def _roles_for_kind(kind: DiscoverKind | None) -> set[ObjectRole] | None:
    if kind is None or kind == DiscoverKind.ALL:
        return None
    mapping = {
        DiscoverKind.LIGHT: {
            ObjectRole.LIGHT_CONTROL,
            ObjectRole.LIGHT_STATUS,
        },
        DiscoverKind.TEMP: {
            ObjectRole.FLOOR_TEMP,
            ObjectRole.ROOM_TEMP,
            ObjectRole.WEATHER,
        },
        DiscoverKind.CLIMATE: {
            ObjectRole.CLIMATE_SETPOINT,
            ObjectRole.HEAT_RELAY_CONTROL,
            ObjectRole.HEAT_RELAY_STATUS,
            ObjectRole.FLOOR_TEMP,
            ObjectRole.ROOM_TEMP,
            ObjectRole.AUTO_HEATING,
        },
        DiscoverKind.SENSOR: {
            ObjectRole.ROOM_TEMP,
            ObjectRole.ROOM_HUMIDITY,
            ObjectRole.FLOOR_TEMP,
            ObjectRole.WEATHER,
            ObjectRole.SENSOR,
        },
        DiscoverKind.ENERGY: {ObjectRole.ENERGY},
        DiscoverKind.HEATING: {
            ObjectRole.HEATING_DIAG,
            ObjectRole.AUTO_HEATING,
            ObjectRole.CLIMATE_SETPOINT,
            ObjectRole.HEAT_RELAY_STATUS,
            ObjectRole.FLOOR_TEMP,
        },
        DiscoverKind.APPLIANCE: {ObjectRole.ZIGBEE_APPLIANCE},
    }
    return mapping[kind]


@lru_cache(maxsize=1)
def _morph() -> MorphAnalyzer:
    import pymorphy3

    return pymorphy3.MorphAnalyzer()


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower().replace("ё", "е")) if len(t) >= 2]


@lru_cache(maxsize=4096)
def _lemma(token: str) -> str:
    parses = _morph().parse(token)
    if not parses:
        return token
    return parses[0].normal_form.replace("ё", "е")


def _normalized_lemmas(text: str) -> set[str]:
    """Surface tokens + lemmas + synonym expansions for fuzzy matching."""
    out: set[str] = set()
    for token in _tokens(text):
        variants = {token, _lemma(token)}
        expanded: set[str] = set()
        for v in variants:
            expanded.add(v)
            for src, dst in _SYNONYMS.items():
                if src in v or v == src:
                    expanded.add(dst)
                    if src in v and src != v:
                        expanded.add(v.replace(src, dst))
        out |= expanded
    return out


def _significant_lemmas(text: str) -> set[str]:
    return {
        lemma
        for lemma in _normalized_lemmas(text)
        if lemma not in _STOP_LEMMAS and len(lemma) >= 3
    }


def _query_matches(query: str | None, obj: Object) -> bool:
    if not query:
        return True
    q = query.lower().strip().replace("ё", "е")
    name = (obj.name or "").lower().replace("ё", "е")
    tags = (obj.tags or "").lower().replace("ё", "е")

    expanded = {q}
    for src, dst in _SYNONYMS.items():
        if src in q:
            expanded.add(q.replace(src, dst))
    # Outdoor lights are tagged "outside" (EN); agents usually ask in Russian.
    # Only expand generic outdoor phrases — not specific names like терраса/крыльцо.
    if any(
        token in q
        for token in (
            "улич",  # уличное, уличный
            "улиц",  # улица, улице (ц ≠ ч)
            "outside",
            "outdoor",
            "снаружи",
            "наружн",
        )
    ) or q in {"двор", "дворе", "на улице"}:
        expanded.add("outside")
    for token in expanded:
        if token in name or token in tags:
            return True

    # Morphological match: «кухне»/«кухню» → «кухня», «крыльце» → «крыльцо».
    query_sig = _significant_lemmas(q)
    if not query_sig:
        return False
    name_sig = _significant_lemmas(f"{name} {tags}")
    return bool(query_sig & name_sig)


def _exclude_master_unless_requested(obj: Object, query: str | None) -> bool:
    name = (obj.name or "").lower()
    if "master" in name and (not query or "master" not in query.lower()):
        return True
    if obj.ga == "1/6/1" and (not query or "master" not in query.lower()):
        return True
    return False


def _to_resolved(obj: Object) -> ResolvedObject:
    return ResolvedObject(
        ga=obj.ga,
        name=obj.name or obj.ga,
        tags=_tag_list(obj.tags),
        role=classify_object(obj),
        datatype=obj.datatype,
    )


async def load_active_objects(
    session: AsyncSession,
    house_id: str,
) -> list[Object]:
    result = await session.execute(
        select(Object).where(Object.house_id == house_id, Object.is_active.is_(True))
    )
    return list(result.scalars().all())


async def resolve_objects(
    session: AsyncSession,
    house_id: str,
    *,
    query: str | None = None,
    kind: DiscoverKind | str | None = None,
    role: ObjectRole | None = None,
) -> ResolveResult:
    if isinstance(kind, str):
        kind = DiscoverKind(kind)

    allowed_roles = _roles_for_kind(kind)
    objs = await load_active_objects(session, house_id)
    matches: list[ResolvedObject] = []

    for obj in objs:
        if not obj.name:
            continue
        if _exclude_master_unless_requested(obj, query):
            continue
        if not _query_matches(query, obj):
            continue
        resolved = _to_resolved(obj)
        if allowed_roles is not None and resolved.role not in allowed_roles:
            continue
        if role is not None and resolved.role != role:
            continue
        matches.append(resolved)

    if not matches:
        return ResolveResult(status="not_found", matches=[])
    if len(matches) > 1 and role is None:
        # Prefer control over status when kind=light and writing isn't specified
        if kind == DiscoverKind.LIGHT and query:
            controls = [m for m in matches if m.role == ObjectRole.LIGHT_CONTROL]
            if len(controls) == 1:
                return ResolveResult(status="ok", matches=controls)
        return ResolveResult(status="ambiguous", matches=matches)
    return ResolveResult(status="ok", matches=matches)


# Curated energy GAs (names from electric meter family)
ENERGY_SUMMARY_GAS = [
    "32/1/35",  # Total P
    "32/1/36",  # Total Q
    "32/1/37",  # Total S
    "32/1/38",  # Total PF
    "32/1/39",  # Total AP energy
    "32/1/7",   # Frequency
    "32/1/1", "32/1/3", "32/1/5",  # Urms L1-L3
    "32/1/11", "32/1/19", "32/1/27",  # Irms L1-L3
    "32/1/13", "32/1/21", "32/1/29",  # P L1-L3
    "32/1/57", "32/1/58", "32/1/59",  # Hour/Daily/Total consumption
]

HEATING_DIAG_GAS = ["34/1/1", "34/1/2", "34/1/3", "34/1/4"]

AUTO_HEATING_GA = "1/7/1"
