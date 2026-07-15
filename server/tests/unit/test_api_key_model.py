from cottage_monitoring.models.api_key import ApiKey


def test_api_key_tablename() -> None:
    assert ApiKey.__tablename__ == "api_keys"
