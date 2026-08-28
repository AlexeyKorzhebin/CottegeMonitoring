from cottage_monitoring.snapshot import HouseSnapshot, area_name_for, leftover_split_area_names

OPS = {
    "get_house_status": {"online_status": "partial", "last_seen": "2026-08-28T00:00:00Z"},
    "list_lights": {
        "items": [
            {"name": "Свет - кухня", "on": True, "area": "кухня", "floor": "1"},
        ],
        "total": 1,
    },
    "get_climate": {
        "auto_heating_enabled": True,
        "zones": [
            {
                "room": "гостиная 1",
                "area": "гостиная",
                "floor": "1",
                "setpoint": 23,
                "room_temp": 21.5,
                "floor_temp": 26.0,
                "relay_on": True,
            }
        ],
    },
    "get_temperature": {
        "items": [
            {"name": "zb_sensor_fl1_living_room_temperature", "source": "air", "value": 21.5, "area": "гостиная", "floor": "1"},
            {"name": "Темп - гостиная 1", "source": "floor", "value": 26.0, "area": "гостиная", "floor": "1"},
            {"name": "weather outdoor", "source": "outdoor", "value": 12.0, "area": None, "floor": "outside"},
        ]
    },
    "get_sensors": {
        "items": [
            {"name": "zb_sensor_fl1_living_room_humidity", "value": 44, "area": "гостиная", "floor": "1"},
        ]
    },
    "get_kettle": {
        "status": "ok",
        "appliance": {
            "name": "ble_teapot_RK-M173S",
            "on": True,
            "temp": 54,
            "setpoint_c": None,
        },
    },
}


def test_partial_house_is_not_online() -> None:
    snap = HouseSnapshot.from_ops("house", OPS)
    assert snap.online is False
    assert snap.auto_heating_enabled is True


def test_areas_and_two_climates_share_guest_area() -> None:
    snap = HouseSnapshot.from_ops("house", OPS)
    assert snap.lights[0].area == "кухня"
    assert snap.lights[0].floor == "1"
    assert snap.climates[0].area == "гостиная"
    assert snap.climates[0].room == "гостиная 1"
    assert snap.climates[0].humidity == 44
    kinds = {s.kind for s in snap.sensors}
    assert {"air", "floor", "humidity", "outdoor"} <= kinds


def test_kettle_without_setpoint_hides_slider_flag() -> None:
    snap = HouseSnapshot.from_ops("house", OPS)
    assert snap.kettle is not None
    assert snap.kettle.temp == 54
    assert snap.kettle.has_setpoint is False
    assert snap.kettle.area == "кухня"


def test_unique_ids_stable() -> None:
    snap = HouseSnapshot.from_ops("house", OPS)
    assert snap.lights[0].unique_id == "house:light:свет_-_кухня"
    assert "ga" not in snap.lights[0].unique_id
    assert "/" not in snap.lights[0].unique_id


def test_same_area_on_two_floors_gets_distinct_ha_names() -> None:
    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {
            "items": [
                {"name": "Свет - холл 1 этаж", "on": False, "area": "холл", "floor": "1"},
                {"name": "Свет - холл 2 этаж", "on": False, "area": "холл", "floor": "2"},
                {"name": "Свет - спальня", "on": False, "area": "спальня", "floor": "1"},
            ]
        },
        "get_climate": {"auto_heating_enabled": False, "zones": []},
        "get_temperature": {"items": []},
        "get_sensors": {"items": []},
        "get_kettle": {},
    }
    snap = HouseSnapshot.from_ops("house", ops)
    floors = snap.floors_by_area()
    assert area_name_for("холл", "1", floors) == "холл (1 этаж)"
    assert area_name_for("холл", "2", floors) == "холл (2 этаж)"
    assert area_name_for("спальня", "1", floors) == "спальня"


def test_guest_fl2_bedroom_does_not_split_first_floor_bedroom() -> None:

    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {
            "items": [
                {"name": "Свет - спальня", "on": False, "area": "спальня", "floor": "1"},
                {"name": "Свет - гостевая", "on": False, "area": "гостевая", "floor": "2"},
            ]
        },
        "get_climate": {"auto_heating_enabled": False, "zones": []},
        "get_temperature": {
            "items": [
                {
                    "name": "zb_sensor_fl1_bedroom_temperature",
                    "source": "air",
                    "value": 22,
                    "area": "спальня",
                    "floor": "1",
                },
                {
                    "name": "zb_sensor_fl2_bedroom_temperature",
                    "source": "air",
                    "value": 24,
                    "area": "гостевая",
                    "floor": "2",
                },
            ]
        },
        "get_sensors": {"items": []},
        "get_kettle": {},
    }
    snap = HouseSnapshot.from_ops("house", ops)
    floors = snap.floors_by_area()
    assert floors["спальня"] == frozenset({"1"})
    assert area_name_for("спальня", "1", floors) == "спальня"
    leftovers = leftover_split_area_names(
        {"спальня", "спальня (1 этаж)", "спальня (2 этаж)", "холл (1 этаж)"},
        floors,
    )
    assert "спальня (1 этаж)" in leftovers
    assert "спальня (2 этаж)" in leftovers
    assert "спальня" not in leftovers


def test_sensor_display_names_are_short() -> None:
    from cottage_monitoring.snapshot import (
        climate_display_name,
        heat_display_name,
        light_display_name,
        place_device_name,
        sensor_display_name,
    )

    assert sensor_display_name(name="zb_sensor_fl1_bedroom_temperature", kind="air") == "Воздух"
    assert sensor_display_name(name="zb_sensor_fl1_bedroom_humidity", kind="humidity") == "Влажность"
    assert sensor_display_name(name="Темп - спальня", kind="floor") == "Пол"
    assert sensor_display_name(name="Темп - гостиная 1", kind="floor") == "Пол 1"
    assert sensor_display_name(name="Темп - гостиная 2", kind="floor") == "Пол 2"
    assert sensor_display_name(name="Темп  - холл 1 этаж", kind="floor") == "Пол"
    assert sensor_display_name(name="Погода - температура", kind="outdoor") == "Температура"
    assert sensor_display_name(name="Погода - ощущение температуры", kind="outdoor") == "Ощущается"
    assert sensor_display_name(name="Погода - ветер - направление", kind="outdoor") == "Направление"
    assert sensor_display_name(name="Погода - ветер - скорость", kind="outdoor") == "Ветер"
    assert sensor_display_name(name="Погода - описание", kind="outdoor") == "Погода"
    assert light_display_name("Свет - спальня") == "Свет"
    assert light_display_name("Свет - гостиная - торшер") == "Торшер"
    assert light_display_name("Свет - подсветка - кухня") == "Подсветка"
    assert light_display_name("Свет - кабинет - тайфайтер") == "Тайфайтер"
    assert climate_display_name("спальня") == "Полы"
    assert climate_display_name("гостиная 1") == "Полы 1"
    assert climate_display_name("холл 1 этаж") == "Полы"
    assert heat_display_name("гостиная 2") == "Нагрев 2"
    assert place_device_name(
        raw_name="zb_sensor_fl1_server_room_temperature",
        area=None,
        floor="1",
    ) == "серверная"
    assert place_device_name(
        raw_name="Погода - температура",
        area=None,
        floor="outside",
    ) == "Улица"

