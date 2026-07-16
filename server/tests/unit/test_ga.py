from cottage_monitoring.utils.ga import ga_lookup_keys, ga_to_dash, ga_to_slash


def test_ga_to_dash() -> None:
    assert ga_to_dash("1/2/3") == "1-2-3"
    assert ga_to_dash("1-2-3") == "1-2-3"


def test_ga_to_slash() -> None:
    assert ga_to_slash("1-2-3") == "1/2/3"
    assert ga_to_slash("1/2/3") == "1/2/3"


def test_ga_lookup_keys() -> None:
    assert ga_lookup_keys("1/2/3") == ["1-2-3", "1/2/3"]
    assert ga_lookup_keys("1-2-3") == ["1-2-3", "1/2/3"]
