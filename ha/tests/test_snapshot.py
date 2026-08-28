from cottage_monitoring.snapshot import HouseSnapshot

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
