from cottage_monitoring.auth.keys import generate_api_key, hash_api_key, verify_api_key


def test_generate_and_verify_roundtrip() -> None:
    raw, prefix = generate_api_key()
    assert raw.startswith("cm_")
    assert raw[:12] == prefix
    h = hash_api_key(raw)
    assert verify_api_key(raw, h)
    assert not verify_api_key(raw + "x", h)
