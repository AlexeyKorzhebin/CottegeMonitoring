from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr

from .const import FLOOR_LABELS, HOUSE_AREA_NAME
from .snapshot import HouseSnapshot

FLOOR_LEVELS = {"1": 1, "2": 2, "outside": 0}


def sync_floors_areas(hass, snap: HouseSnapshot) -> None:
    floors = fr.async_get(hass)
    areas = ar.async_get(hass)
    floor_ids: dict[str, str] = {}
    for key, label in FLOOR_LABELS.items():
        existing = next((f for f in floors.async_list_floors() if f.name == label), None)
        entry = existing or floors.async_create(label, level=FLOOR_LEVELS[key])
        floor_ids[key] = entry.floor_id
    home = next((a for a in areas.async_list_areas() if a.name == HOUSE_AREA_NAME), None)
    if home is None:
        areas.async_create(HOUSE_AREA_NAME)
    pairs: set[tuple[object, str]] = set()
    for item in (*snap.lights, *snap.climates, *snap.sensors):
        if item.floor == "outside":
            pairs.add((item.floor, FLOOR_LABELS["outside"]))
        elif item.area:
            pairs.add((item.floor, item.area))
    if snap.kettle and snap.kettle.area:
        pairs.add((snap.kettle.floor, snap.kettle.area))
    for floor_key, area_name in pairs:
        existing = next((a for a in areas.async_list_areas() if a.name == area_name), None)
        floor_id = floor_ids.get(floor_key) if floor_key else None
        if existing is None:
            areas.async_create(area_name, floor_id=floor_id)
        elif floor_id and existing.floor_id != floor_id:
            areas.async_update(existing.id, floor_id=floor_id)
