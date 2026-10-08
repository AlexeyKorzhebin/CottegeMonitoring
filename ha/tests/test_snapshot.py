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


def test_energy_snapshot_keeps_six_keys_drops_phases() -> None:
    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {"items": []},
        "get_climate": {"auto_heating_enabled": False, "zones": []},
        "get_temperature": {"items": []},
        "get_sensors": {"items": []},
        "get_sensors_battery": {"items": []},
        "get_kettle": {},
        "get_energy_status": {
            "items": [
                {"ga": "32/1/35", "name": "Total P", "value": 420, "units": "W"},
                {"ga": "32/1/36", "name": "Total Q", "value": 10, "units": "var"},
                {"ga": "32/1/39", "name": "AP energy", "value": 999, "units": "kWh"},
                {"ga": "32/1/7", "name": "Frequency", "value": 50.02, "units": "Hz"},
                {"ga": "32/1/59", "name": "consumption Total", "value": 1234.5, "units": "kWh"},
                {"ga": "32/1/57", "name": "Hour", "value": 1.2, "units": "kWh"},
                {"ga": "32/1/58", "name": "Daily", "value": 18.0, "units": "kWh"},
                {"ga": "32/1/38", "name": "PF", "value": 0.97, "units": ""},
                {"ga": "32/1/1", "name": "Urms L1", "value": 230, "units": "V"},
            ]
        },
    }
    snap = HouseSnapshot.from_ops("house", ops)
    energy = {s.kind: s for s in snap.sensors if s.kind in {"power", "frequency", "meter", "hour", "daily", "pf"}}
    assert set(energy) == {"power", "frequency", "meter", "hour", "daily", "pf"}
    assert energy["power"].value == 420
    assert energy["meter"].value == 1234.5
    assert energy["meter"].unique_id == "house:energy:meter"
    assert energy["power"].unique_id == "house:energy:power"
    assert all(s.area is None and s.floor is None for s in energy.values())
    from cottage_monitoring.snapshot import sensor_display_name
    assert sensor_display_name(name="ignored", kind="power") == "Сейчас"
    assert sensor_display_name(name="ignored", kind="frequency") == "Частота"
    assert sensor_display_name(name="ignored", kind="meter") == "Счётчик"
    assert sensor_display_name(name="ignored", kind="hour") == "За час"
    assert sensor_display_name(name="ignored", kind="daily") == "За сутки"
    assert sensor_display_name(name="ignored", kind="pf") == "PF"


def test_energy_missing_ga_skips_only_that_key() -> None:
    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {"items": []},
        "get_climate": {"auto_heating_enabled": False, "zones": []},
        "get_temperature": {"items": []},
        "get_sensors": {"items": []},
        "get_kettle": {},
        "get_energy_status": {"items": [{"ga": "32/1/35", "name": "Total P", "value": 1}]},
    }
    snap = HouseSnapshot.from_ops("house", ops)
    kinds = {s.kind for s in snap.sensors}
    assert "power" in kinds
    assert "meter" not in kinds


def test_battery_sensors_and_display_name() -> None:
    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {"items": []},
        "get_climate": {"auto_heating_enabled": False, "zones": []},
        "get_temperature": {"items": []},
        "get_sensors": {
            "items": [
                {"name": "zb_sensor_fl1_living_room_humidity", "value": 44, "area": "гостиная", "floor": "1"},
            ]
        },
        "get_sensors_battery": {
            "items": [
                {"name": "zb_sensor_fl1_bedroom_battery", "value": 91, "area": "спальня", "floor": "1"},
            ]
        },
        "get_kettle": {},
    }
    snap = HouseSnapshot.from_ops("house", ops)
    bats = [s for s in snap.sensors if s.kind == "battery"]
    hums = [s for s in snap.sensors if s.kind == "humidity"]
    assert len(bats) == 1
    assert bats[0].area == "спальня"
    assert bats[0].unique_id == "house:sensor_battery:zb_sensor_fl1_bedroom_battery"
    assert len(hums) == 1
    from cottage_monitoring.snapshot import sensor_display_name, sensor_ha_profile
    assert sensor_display_name(name="zb_sensor_fl1_bedroom_battery", kind="battery") == "Батарея"
    assert sensor_ha_profile("meter")["state_class"] == "total_increasing"
    assert sensor_ha_profile("hour")["state_class"] == "total"
    assert sensor_ha_profile("daily")["state_class"] == "total"
    assert sensor_ha_profile("battery") == {
        "device_class": "battery",
        "unit": "%",
        "state_class": "measurement",
    }


def test_climate_zone_uses_its_own_floor_air_and_humidity() -> None:
    """get_climate.floor_temp путает соседние зоны; карточка берёт датчик этой комнаты."""
    from cottage_monitoring.snapshot import climate_shown_temperature, pick_area_entity

    ops = {
        "get_house_status": {"online_status": "online"},
        "list_lights": {"items": []},
        "get_climate": {
            "auto_heating_enabled": True,
            "zones": [
                {"room": "гостиная 1", "area": "гостиная", "floor": "1", "setpoint": 22, "room_temp": None, "floor_temp": 21.78, "relay_on": False},
                {"room": "гостиная 2", "area": "гостиная", "floor": "1", "setpoint": 22, "room_temp": None, "floor_temp": 21.78, "relay_on": False},
                {"room": "холл 1 этаж", "area": "холл", "floor": "1", "setpoint": 12, "room_temp": None, "floor_temp": 16.14, "relay_on": False},
                {"room": "холл 2 этаж", "area": "холл", "floor": "2", "setpoint": 12, "room_temp": None, "floor_temp": 25.92, "relay_on": False},
                {"room": "Тимнина комната", "area": "Тимнина комната", "floor": "2", "setpoint": 12, "room_temp": None, "floor_temp": None, "relay_on": False},
                {"room": "тамбур", "area": "тамбур", "floor": "1", "setpoint": 12, "room_temp": None, "floor_temp": 16.14, "relay_on": False},
            ],
        },
        "get_temperature": {
            "items": [
                {"name": "zb_sensor_fl1_living_room_temperature", "source": "air", "value": 19.87, "area": "гостиная", "floor": "1"},
                {"name": "zb_sensor_fl1_hall_temperature", "source": "air", "value": 19.3, "area": "холл", "floor": "1"},
                {"name": "zb_sensor_fl2_hall_temperature", "source": "air", "value": 22.54, "area": "холл", "floor": "2"},
                {"name": "zb_sensor_fl1_server_room_temperature", "source": "air", "value": 19.23, "area": None, "floor": "1"},
                {"name": "Темп - гостиная 1", "source": "floor", "value": 21.1, "area": "гостиная", "floor": "1"},
                {"name": "Темп - гостиная 2", "source": "floor", "value": 21.38, "area": "гостиная", "floor": "1"},
                {"name": "Темп  - холл 1 этаж", "source": "floor", "value": 21.24, "area": "холл", "floor": "1"},
                {"name": "Темп - холл 2 этаж", "source": "floor", "value": 18.76, "area": "холл", "floor": "2"},
                {"name": "Темп - Тимина комната", "source": "floor", "value": 25.92, "area": "Тимнина комната", "floor": "2"},
                {"name": "Темп - тамбур", "source": "floor", "value": 16.14, "area": "тамбур", "floor": "1"},
            ]
        },
        "get_sensors": {
            "items": [
                {"name": "zb_sensor_fl1_living_room_humidity", "value": 37, "area": "гостиная", "floor": "1"},
                {"name": "zb_sensor_fl1_hall_humidity", "value": 39, "area": "холл", "floor": "1"},
                {"name": "zb_sensor_fl2_hall_humidity", "value": 45, "area": "холл", "floor": "2"},
            ]
        },
        "get_kettle": {},
    }
    snap = HouseSnapshot.from_ops("house", ops)
    by_room = {zone.room: zone for zone in snap.climates}
    assert by_room["гостиная 1"].floor_temp == 21.1
    assert by_room["гостиная 2"].floor_temp == 21.38
    assert by_room["гостиная 1"].room_temp == 19.87
    assert by_room["гостиная 1"].humidity == 37
    assert by_room["холл 1 этаж"].floor_temp == 21.24
    assert by_room["холл 2 этаж"].floor_temp == 18.76
    assert by_room["холл 1 этаж"].room_temp == 19.3
    assert by_room["холл 2 этаж"].room_temp == 22.54
    assert by_room["холл 1 этаж"].humidity == 39
    assert by_room["холл 2 этаж"].humidity == 45
    assert by_room["Тимнина комната"].floor_temp == 25.92
    assert by_room["тамбур"].room_temp is None
    assert by_room["тамбур"].humidity is None
    assert climate_shown_temperature(floor_temp=21.1, room_temp=19.87) == 21.1
    assert climate_shown_temperature(floor_temp=None, room_temp=19.3) == 19.3

    uids = snap.area_climate_sensor_uids()
    assert uids["гостиная"]["air"] == "house:sensor_air:zb_sensor_fl1_living_room_temperature"
    assert uids["гостиная"]["humidity"] == "house:sensor_humidity:zb_sensor_fl1_living_room_humidity"
    assert uids["холл (1 этаж)"]["humidity"] == "house:sensor_humidity:zb_sensor_fl1_hall_humidity"
    assert uids["холл (2 этаж)"]["air"] == "house:sensor_air:zb_sensor_fl2_hall_temperature"
    assert "серверная" not in uids
    assert pick_area_entity(None, "sensor.vozdukh", current_is_ours=True) == (True, "sensor.vozdukh")
    assert pick_area_entity("sensor.vozdukh", "sensor.vozdukh", current_is_ours=True) == (False, "sensor.vozdukh")
    assert pick_area_entity("sensor.ruchnoy", "sensor.vozdukh", current_is_ours=False) == (False, "sensor.ruchnoy")
    assert pick_area_entity("sensor.staryy_pol", None, current_is_ours=True) == (True, None)

