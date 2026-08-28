"""The Ops catalog (design spec §12) — the single source of both Nord faces.

Adding semantics means adding a row here. A tool that is not in this file cannot
appear on MCP, and an Op that is here always appears on both faces; the drift
tests fail otherwise.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import ModuleType
from typing import Any

from pydantic import BaseModel

from cottage_monitoring.ops import houses as houses_ops
from cottage_monitoring.ops import params
from cottage_monitoring.ops.registry import register, registry
from cottage_monitoring.ops.spec import OpSpec
from cottage_monitoring.services import agent_actions


def _handler(
    module: ModuleType,
    attr: str,
    *,
    blank_to_none: tuple[str, ...] = (),
) -> Callable[..., Awaitable[dict]]:
    """Bind a catalog row to its service function, looked up at call time.

    Late lookup keeps handlers patchable in tests and gives one place to turn the
    empty-string tool defaults back into the ``None`` the services expect (an
    empty query means "no filter", not "match the empty string").
    """
    if not hasattr(module, attr):
        raise AttributeError(f"{module.__name__} has no handler named {attr!r}")

    async def handler(session: Any, *args: Any, **op_params: Any) -> dict:
        for field in blank_to_none:
            if op_params.get(field) == "":
                op_params[field] = None
        return await getattr(module, attr)(session, *args, **op_params)

    handler.__name__ = attr
    handler.__qualname__ = f"{module.__name__}.{attr}"
    return handler


def _op(
    name: str,
    permission: str,
    description: str,
    handler: Callable[..., Awaitable[dict]],
    *,
    house_scoped: bool = True,
    params_model: type[BaseModel] = params.NoParams,
) -> OpSpec:
    return OpSpec(
        name=name,
        permission=permission,
        house_scoped=house_scoped,
        description=description,
        handler=handler,
        params_model=params_model,
    )


def _catalog() -> tuple[OpSpec, ...]:
    return (
        _op(
            "list_houses",
            "read",
            "List the houses this API key may act on. Call first when more than one is possible.",
            _handler(houses_ops, "list_houses"),
            house_scoped=False,
        ),
        _op(
            "get_house_status",
            "read",
            "Online status, last_seen, object counts for the house.",
            _handler(agent_actions, "get_house_status"),
        ),
        _op(
            "discover",
            "read",
            "Find objects by name/query and kind: light, temp, climate, sensor, energy, "
            "heating, appliance, all.",
            _handler(agent_actions, "discover", blank_to_none=("query",)),
            params_model=params.DiscoverParams,
        ),
        _op(
            "get_temperature",
            "read",
            "Room air temperature (Zigbee 33/1/*), floor temperature (1/3/*), and outdoor "
            "weather. Prefer air sensors for room comfort.",
            _handler(agent_actions, "get_temperatures", blank_to_none=("query",)),
            params_model=params.QueryParams,
        ),
        _op(
            "get_sensors",
            "read",
            "Read sensors by kind or query: temp, humidity, meter, climate, etc.",
            _handler(agent_actions, "get_sensors", blank_to_none=("query",)),
            params_model=params.GetSensorsParams,
        ),
        _op(
            "list_lights",
            "read",
            "List lights with current on/off state.",
            _handler(agent_actions, "list_lights", blank_to_none=("query",)),
            params_model=params.QueryParams,
        ),
        _op(
            "set_light",
            "write",
            "Turn a light on or off by room/name query (single fixture).",
            _handler(agent_actions, "set_light"),
            params_model=params.SetLightParams,
        ),
        _op(
            "set_lights",
            "write",
            "Turn multiple lights on/off in one MQTT batch. Use for zones: «1 этаж», "
            "«уличное», «2 этаж». skip_unchanged (default true) uses status feedback 1/2/*, "
            "not control 1/1/* (wall switches update status only). Prefer over looping "
            "set_light — one request_id, one ack.",
            _handler(agent_actions, "set_lights"),
            params_model=params.SetLightsParams,
        ),
        _op(
            "set_commands",
            "write",
            "Send arbitrary GA/value commands in batch. Input: items=[{ga,value}, ...]. "
            "Server groups items by device and sends minimal MQTT commands. skip_unchanged "
            "(default true) compares against status sibling when writing a control GA "
            "(1/2/* for lights, 1/5/* for heat, *_state for BLE), not the control itself.",
            _handler(agent_actions, "set_commands", blank_to_none=("comment",)),
            params_model=params.SetCommandsParams,
        ),
        _op(
            "get_climate",
            "read",
            "Underfloor heating: setpoints, floor/room temps, relay status, auto algorithm "
            "state. Setpoint alone does not enable heating — relays are managed by auto "
            "balancing (1/7/1).",
            _handler(agent_actions, "get_climate", blank_to_none=("query",)),
            params_model=params.QueryParams,
        ),
        _op(
            "set_climate",
            "write",
            "Set underfloor heating setpoint (°C) for a room. Does not force relay on. "
            "Use force_relay only for debug manual override.",
            _handler(agent_actions, "set_climate_setpoint"),
            params_model=params.SetClimateParams,
        ),
        _op(
            "set_auto_heating",
            "write",
            "Toggle underfloor auto-heating algorithm on GA 1/7/1. Turning off lets LM Lua "
            "drop all floor relays. Distinct from per-zone relay status.",
            _handler(agent_actions, "set_auto_heating"),
            params_model=params.SetAutoHeatingParams,
        ),
        _op(
            "get_energy_status",
            "read",
            "Electricity: total power, per-phase voltage/current/power, frequency, "
            "hourly/daily/total consumption.",
            _handler(agent_actions, "get_energy_status"),
        ),
        _op(
            "get_heating_diagnostics",
            "read",
            "Warm floor diagnostics from 34/1/* (modes, blocks, weather k_base, power limit) "
            "and auto algorithm state 1/7/1.",
            _handler(agent_actions, "get_heating_diagnostics"),
        ),
        _op(
            "get_kettle",
            "read",
            "Read BLE teapot status: appliance.temp is current water temperature, "
            "appliance.setpoint_c is the target when a setpoint object exists "
            "(cmd 33/1/39, state 33/1/38, temp 33/1/37).",
            _handler(agent_actions, "get_kettle"),
        ),
        _op(
            "set_kettle",
            "write",
            "Control BLE teapot Redmond RK-M173S. on and/or setpoint_c (40–100). "
            "Never write °C to cmd 33/1/39. Prefer get_kettle before/after.",
            _handler(agent_actions, "set_kettle"),
            params_model=params.SetKettleParams,
        ),
        _op(
            "get_command_status",
            "read",
            "Poll command status by request_id after set_light/set_climate/set_kettle.",
            _handler(agent_actions, "get_command_status"),
            params_model=params.GetCommandStatusParams,
        ),
    )


def load_catalog() -> None:
    """Register every Op and rebuild the MCP tools from it. Idempotent.

    Called explicitly from the FastAPI lifespan (and from tests) so the catalog
    is never a side effect of whichever module happened to be imported first.
    """
    for spec in _catalog():
        if spec.name not in registry:
            register(spec)

    # Local import: the ops layer wires the MCP face here, the face does not
    # reach back into the catalog.
    from cottage_monitoring.mcp.server import register_op_tools

    register_op_tools()
