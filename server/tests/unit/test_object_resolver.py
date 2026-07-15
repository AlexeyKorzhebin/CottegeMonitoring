from cottage_monitoring.models.object import Object
from cottage_monitoring.services.object_resolver import (
    ObjectRole,
    classify_object,
    resolve_objects,
)


def _obj(ga: str, name: str, tags: str) -> Object:
    return Object(
        house_id="h1",
        ga=ga,
        name=name,
        datatype=9001,
        tags=tags,
        is_active=True,
        is_timeseries=False,
    )


def test_classify_light_control() -> None:
    o = _obj("1/1/7", "Свет - кухня", "1floor,control,light")
    assert classify_object(o) == ObjectRole.LIGHT_CONTROL


def test_classify_room_temp_zb() -> None:
    o = _obj("33/1/13", "zb_sensor_fl1_kitchen_temperature", "floor1,temperature,zb_sensor")
    assert classify_object(o) == ObjectRole.ROOM_TEMP


def test_classify_floor_temp() -> None:
    o = _obj("1/3/7", "Темп - кухня", "1floor,heat,temp")
    assert classify_object(o) == ObjectRole.FLOOR_TEMP


def test_classify_setpoint() -> None:
    o = _obj("1/6/7", "Уставка ТП - кухня", "1floor,heat,setpoint,temp")
    assert classify_object(o) == ObjectRole.CLIMATE_SETPOINT


def test_query_matches_outdoor_russian_to_outside_tag() -> None:
    from cottage_monitoring.services.object_resolver import _query_matches

    o = _obj("1/1/1", "Свет - крыльцо", "control,light,outside")
    assert _query_matches("уличное освещение", o) is True
    assert _query_matches("улица", o) is True
    assert _query_matches("outdoor lights", o) is True
    assert _query_matches("outside", o) is True
    assert _query_matches("кухня", o) is False


def test_query_matches_russian_cases() -> None:
    from cottage_monitoring.services.object_resolver import _query_matches

    kitchen = _obj("1/1/7", "Свет - кухня", "1floor,control,light")
    porch = _obj("1/1/1", "Свет - крыльцо", "control,light,outside")
    terrace = _obj("1/1/5", "Свет - терраса", "control,light,outside")
    guest = _obj("1/1/3", "Свет - гостевая", "1floor,control,light")
    nastya = _obj("1/1/9", "Свет - спальня Насти", "1floor,control,light")

    assert _query_matches("кухне", kitchen) is True
    assert _query_matches("свет в кухне", kitchen) is True
    assert _query_matches("кухню", kitchen) is True
    assert _query_matches("крыльце", porch) is True
    assert _query_matches("террасу", terrace) is True
    assert _query_matches("гостевой", guest) is True
    assert _query_matches("в гостевую", guest) is True
    assert _query_matches("настиной", nastya) is True
    assert _query_matches("террасу", kitchen) is False
    assert _query_matches("кухне", porch) is False


async def test_resolve_kitchen_light_unique(db_session) -> None:
    import pytest
    from cottage_monitoring.services.house_service import ensure_house

    pytestmark = pytest.mark.integration

    house_id = "resolver-test-house"
    await ensure_house(house_id, session=db_session)
    db_session.add(
        Object(
            house_id=house_id,
            ga="1/1/7",
            name="Свет - кухня",
            datatype=1001,
            tags="1floor,control,light",
            is_active=True,
            is_timeseries=False,
        )
    )
    db_session.add(
        Object(
            house_id=house_id,
            ga="1/2/7",
            name="Свет - кухня :status",
            datatype=1001,
            tags="light,status",
            is_active=True,
            is_timeseries=False,
        )
    )
    await db_session.commit()

    result = await resolve_objects(
        db_session, house_id, query="кухня", kind="light", role=ObjectRole.LIGHT_CONTROL
    )
    assert result.status == "ok"
    assert len(result.matches) == 1
    assert result.matches[0].ga == "1/1/7"
