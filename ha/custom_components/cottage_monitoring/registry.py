from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr

from .const import FLOOR_LABELS, HOUSE_AREA_NAME
from .snapshot import HouseSnapshot, leftover_split_area_names, place_device_name

FLOOR_LEVELS = {"1": 1, "2": 2, "outside": 0}


def _item_area_name(item, floors_by_area) -> str | None:
    raw = getattr(item, "name", None) or getattr(item, "room", None) or ""
    return place_device_name(
        raw_name=raw,
        area=item.area,
        floor=item.floor,
        floors_by_area=floors_by_area,
    )


def sync_floors_areas(hass, snap: HouseSnapshot) -> None:
    floors = fr.async_get(hass)
    areas = ar.async_get(hass)
    ents = er.async_get(hass)
    floor_ids: dict[str, str] = {}
    for key, label in FLOOR_LABELS.items():
        existing = next((f for f in floors.async_list_floors() if f.name == label), None)
        entry = existing or floors.async_create(label, level=FLOOR_LEVELS[key])
        floor_ids[key] = entry.floor_id
    home = next((a for a in areas.async_list_areas() if a.name == HOUSE_AREA_NAME), None)
    if home is None:
        areas.async_create(HOUSE_AREA_NAME)
    pairs: set[tuple[object, str]] = set()
    floors_by_area = snap.floors_by_area()
    uid_to_area: dict[str, str] = {}
    for item in (*snap.lights, *snap.climates, *snap.sensors):
        name = _item_area_name(item, floors_by_area)
        if name:
            uid_to_area[item.unique_id] = name
            if name != HOUSE_AREA_NAME:
                pairs.add((item.floor, name))
    if snap.kettle:
        name = _item_area_name(snap.kettle, floors_by_area)
        if name:
            uid_to_area[snap.kettle.unique_id] = name
            if name != HOUSE_AREA_NAME:
                pairs.add((snap.kettle.floor, name))
    for floor_key, area_name in pairs:
        existing = next((a for a in areas.async_list_areas() if a.name == area_name), None)
        floor_id = floor_ids.get(floor_key) if floor_key else None
        if existing is None:
            areas.async_create(area_name, floor_id=floor_id)
        elif floor_id and existing.floor_id != floor_id:
            areas.async_update(existing.id, floor_id=floor_id)

    area_by_name = {a.name: a for a in areas.async_list_areas()}
    for entry in list(ents.entities.values()):
        target = uid_to_area.get(entry.unique_id)
        if not target:
            continue
        area = area_by_name.get(target)
        if area is None or entry.area_id == area.id:
            continue
        ents.async_update_entity(entry.entity_id, area_id=area.id)

    occupied = {e.area_id for e in ents.entities.values() if e.area_id}
    leftover = leftover_split_area_names(
        {a.name for a in areas.async_list_areas()},
        floors_by_area,
    )
    for name in leftover:
        area = area_by_name.get(name)
        if area is None or area.id in occupied:
            continue
        areas.async_delete(area.id)
