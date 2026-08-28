"""Canonical room/floor labels for read-Ops (HA Areas/Floors consume these)."""

from __future__ import annotations

import re
from typing import Literal

Floor = Literal["1", "2", "outside"]

_ZB_NAME_RE = re.compile(
    r"zb_sensor_fl(?P<fl>[12])_(?P<room>.+)_(?:temperature|humidity|battery)$",
    re.IGNORECASE,
)

_ZB_ROOM: dict[str, str] = {
    "kitchen": "кухня",
    "living_room": "гостиная",
    "livingroom": "гостиная",
    "bedroom": "спальня",
    "guest_room": "гостевая",
    "guest": "гостевая",
    "office": "кабинет",
    "hallway": "холл",
    "hall": "холл",
    "bathroom": "ванная",
    "bath": "ванная",
    "tambour": "тамбур",
    "nastya": "Настина комната",
    "tim": "Тимнина комната",
}

_KNX_PREFIXES = (
    "свет - ",
    "уставка тп - ",
    "темп - ",
    "тп - ",
)

# Longer phrases first.
_NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("настина комната", "Настина комната"),
    ("тимнина комната", "Тимнина комната"),
    ("тимнина", "Тимнина комната"),
    ("настин", "Настина комната"),
    ("спальня насти", "Настина комната"),
    ("гостиная", "гостиная"),
    ("гостев", "гостевая"),
    ("кухн", "кухня"),
    ("спальн", "спальня"),
    ("кабинет", "кабинет"),
    ("тамбур", "тамбур"),
    ("холл", "холл"),
    ("ванн", "ванная"),
    ("крыльц", "крыльцо"),
    ("террас", "терраса"),
    ("балкон", "балкон"),
    ("зал", "гостиная"),
    ("настя", "Настина комната"),
)


def _tagset(tags: list[str] | str) -> set[str]:
    parts = tags.split(",") if isinstance(tags, str) else tags
    return {t.strip().lower() for t in parts if t and t.strip()}


def floor_from_tags(tags: list[str] | str) -> Floor | None:
    tagset = _tagset(tags)
    if tagset & {"outside", "outdoor", "weather"}:
        return "outside"
    if tagset & {"1floor", "floor1", "fl1"}:
        return "1"
    if tagset & {"2floor", "floor2", "fl2"}:
        return "2"
    return None


def floor_from_name(name: str) -> Floor | None:
    m = _ZB_NAME_RE.search((name or "").strip())
    if m:
        return m.group("fl")  # type: ignore[return-value]
    return None


def _strip_knx_prefix(name: str) -> str:
    n = (name or "").strip()
    low = n.lower().replace("ё", "е")
    for prefix in _KNX_PREFIXES:
        if low.startswith(prefix):
            return n[len(prefix) :].strip()
    if " :status" in low:
        return _strip_knx_prefix(n[: low.index(" :status")])
    return n


def _strip_zone_index(area: str) -> str:
    return re.sub(r"\s+[12]$", "", area).strip()


def area_from_name(name: str, tags: list[str] | str = "") -> str | None:
    _ = tags
    raw = (name or "").strip()
    if not raw:
        return None
    zb = _ZB_NAME_RE.search(raw)
    if zb:
        room_key = zb.group("room").lower()
        if room_key in _ZB_ROOM:
            return _ZB_ROOM[room_key]
    surface = _strip_knx_prefix(raw)
    low = surface.lower().replace("ё", "е")
    for needle, canonical in _NAME_HINTS:
        if needle in low:
            return _strip_zone_index(canonical) if canonical == "гостиная" else canonical
    if low in {"гостиная 1", "гостиная 2"}:
        return "гостиная"
    return None


def placement(*, name: str, tags: list[str] | str) -> dict[str, str]:
    out: dict[str, str] = {}
    floor = floor_from_tags(tags) or floor_from_name(name)
    area = area_from_name(name, tags)
    if floor:
        out["floor"] = floor
    if area:
        out["area"] = area
    return out
