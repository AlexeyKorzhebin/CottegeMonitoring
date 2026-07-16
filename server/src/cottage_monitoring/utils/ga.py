"""Canonical GA helpers: slash for API/events, dash for current_state storage."""


def ga_to_dash(ga: str | None) -> str:
    """Normalize GA to dash form (e.g. 1-2-3) for storage keys / MQTT topic suffixes."""
    return (ga or "").replace("/", "-")


def ga_to_slash(ga: str | None) -> str:
    """Normalize GA to slash form (e.g. 1/2/3) for API and event payloads."""
    return (ga or "").replace("-", "/")


def ga_lookup_keys(ga: str | None) -> list[str]:
    """Both forms for lookups against mixed historical data."""
    dash = ga_to_dash(ga)
    slash = ga_to_slash(dash)
    if dash == slash:
        return [dash] if dash else []
    return [dash, slash]
