from cottage_monitoring.ai_srv_mapping import (
    availability_online,
    bytes_to_gib,
    load_catalog,
    mib_to_gib,
    numeric_or_sentinel,
    offline_numeric_gas,
    sensor_loss_or_sentinel,
    shutdown_temp,
    shutdown_text,
    text_or_unknown,
)


def test_catalog_has_19_objects_and_prefix() -> None:
    cat = load_catalog()
    assert len(cat) == 19
    gas = [o["ga"] for o in cat]
    assert gas[0] == "35/1/1"
    assert gas[-1] == "35/1/19"
    assert gas == [f"35/1/{i}" for i in range(1, 20)]
    for o in cat:
        assert o["name"].startswith("AI-SRV - ")
        assert o["tags"] == "monitoring, gpu, ai-srv"


def test_numeric_fresh_and_sentinel() -> None:
    assert numeric_or_sentinel(52.0, "fresh") == 52.0
    assert numeric_or_sentinel(52.0, "unknown") == -1
    assert numeric_or_sentinel(None, "fresh") == -1
    assert numeric_or_sentinel(0, "fresh") == 0


def test_sensor_loss_null_is_zero() -> None:
    assert sensor_loss_or_sentinel(None) == 0
    assert sensor_loss_or_sentinel(12.5) == 12.5


def test_conversions() -> None:
    assert mib_to_gib(65536, "fresh") == 64.0
    assert mib_to_gib(None, "fresh") == -1
    assert abs(bytes_to_gib(1073741824, "fresh") - 1.0) < 1e-9


def test_text_and_shutdown() -> None:
    assert text_or_unknown(None) == "unknown"
    assert text_or_unknown("connected") == "connected"
    assert shutdown_text(None, "reason") == "none"
    assert shutdown_text({"reason": "overheat"}, "reason") == "overheat"
    assert shutdown_temp(None) == -1
    assert shutdown_temp({"last_temperature_c": 84}) == 84


def test_availability_and_offline_gas() -> None:
    assert availability_online("online") is True
    assert availability_online("offline") is False
    assert availability_online(b"online") is True
    gas = offline_numeric_gas()
    assert "35/1/1" not in gas
    assert "35/1/14" not in gas
    assert "35/1/15" not in gas
    assert "35/1/2" in gas
    assert "35/1/18" in gas
