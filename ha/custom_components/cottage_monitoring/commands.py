from __future__ import annotations


def lights_turn_on_body(name: str) -> tuple[str, dict]:
    return "set_lights", {"query": name, "on": True, "skip_unchanged": False}


def lights_turn_off_body(name: str) -> tuple[str, dict]:
    return "set_lights", {"query": name, "on": False, "skip_unchanged": False}


def climate_set_temp_body(room: str, temp: float) -> tuple[str, dict]:
    return "set_climate", {"query": room, "setpoint_c": temp}


def auto_heating_body(on: bool) -> tuple[str, dict]:
    return "set_auto_heating", {"on": on}


def kettle_on_body() -> tuple[str, dict]:
    return "set_kettle", {"on": True}


def kettle_off_body() -> tuple[str, dict]:
    return "set_kettle", {"on": False}


def kettle_setpoint_body(c: float) -> tuple[str, dict]:
    return "set_kettle", {"setpoint_c": c}
