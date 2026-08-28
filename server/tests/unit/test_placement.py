from cottage_monitoring.services.placement import area_from_name, floor_from_tags, placement


def test_floor_from_knx_and_zigbee_tags() -> None:
    assert floor_from_tags("1floor,control,light") == "1"
    assert floor_from_tags(["floor1", "temperature", "zb_sensor"]) == "1"
    assert floor_from_tags("2floor,heat,setpoint") == "2"
    assert floor_from_tags(["floor2"]) == "2"
    assert floor_from_tags("control,light,outside") == "outside"
    assert floor_from_tags("outside,weather") == "outside"
    assert floor_from_tags("control,light") is None


def test_area_from_knx_light_name() -> None:
    assert area_from_name("Свет - кухня") == "кухня"
    assert area_from_name("Свет - гостиная") == "гостиная"
    assert area_from_name("Свет - гостиная - торшер") == "гостиная"
    assert area_from_name("Свет - крыльцо", "control,light,outside") == "крыльцо"
    assert area_from_name("Свет - спальня Насти") == "Настина комната"
    assert area_from_name("Свет - спальня Тима") == "Тимнина комната"
    assert area_from_name("Свет - спальня Тимы") == "Тимнина комната"
    assert area_from_name("Свет - спальня") == "спальня"
    assert area_from_name("Уставка ТП - гостиная 1") == "гостиная"
    assert area_from_name("Уставка ТП - гостиная 2") == "гостиная"
    assert area_from_name("Уставка ТП - Настина комната") == "Настина комната"
    assert area_from_name("Уставка ТП - Тимнина комната") == "Тимнина комната"
    assert area_from_name("Темп - Тимина комната") == "Тимнина комната"
    assert area_from_name("ТП - Тимина комната") == "Тимнина комната"
    assert area_from_name("Темп - кабинет") == "кабинет"


def test_area_from_zigbee_english_name() -> None:
    assert area_from_name("zb_sensor_fl1_kitchen_temperature") == "кухня"
    assert area_from_name("zb_sensor_fl1_living_room_humidity") == "гостиная"
    assert placement(
        name="zb_sensor_fl1_living_room_temperature",
        tags="floor1,temperature,zb_sensor",
    ) == {"floor": "1", "area": "гостиная"}
    assert area_from_name("zb_sensor_fl1_bedroom_temperature") == "спальня"
    assert area_from_name("zb_sensor_fl2_bedroom_temperature") == "гостевая"
    assert area_from_name("zb_sensor_fl2_bedroom_humidity") == "гостевая"
    assert area_from_name("zb_sensor_fl2_tima_bedroom_temperature") == "Тимнина комната"
    assert area_from_name("zb_sensor_fl2_nastya_bedroom_humidity") == "Настина комната"
    assert placement(
        name="zb_sensor_fl2_bedroom_temperature",
        tags="floor2,temperature,zb_sensor",
    ) == {"floor": "2", "area": "гостевая"}


def test_synonyms_zal_nastya() -> None:
    assert area_from_name("Свет - зал") == "гостиная"
    assert area_from_name("Свет - Настя") == "Настина комната"


def test_placement_omits_missing_keys() -> None:
    assert placement(name="unknown_device_xyz", tags="") == {}
    assert "floor" not in placement(name="Свет - кухня", tags="control,light")
