"""High-level actions for MCP semantic tools."""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.auth.context import ApiKeyContext
from cottage_monitoring.deps import redis_cache
from cottage_monitoring.models.command import Command
from cottage_monitoring.models.house import House
from cottage_monitoring.models.object import Object
from cottage_monitoring.models.state import CurrentState
from cottage_monitoring.services.ceiling_light_params import params_for_relay
from cottage_monitoring.services.command_service import send_command
from cottage_monitoring.services.command_validation import (
    validate_batch_size,
    validate_command_value,
)
from cottage_monitoring.services.object_resolver import (
    AUTO_HEATING_GA,
    ENERGY_SUMMARY_GAS,
    HEATING_DIAG_GAS,
    DiscoverKind,
    ObjectRole,
    _is_zone_query,
    classify_object,
    resolve_objects,
)
from cottage_monitoring.services.placement import placement

logger = structlog.get_logger(__name__)

# Zigbee plug powering AI-SRV + movie projector relay (LM GA SoT).
AI_SRV_SWITCHER_CMD_GA = "32/6/5"
AI_SRV_SWITCHER_STATUS_GA = "32/6/6"
AI_SRV_PLUG_POWER_W_GA = "35/1/20"
AI_SRV_PLUG_CURRENT_A_GA = "35/1/21"
AI_SRV_PLUG_VOLTAGE_V_GA = "35/1/22"
AI_SRV_PLUG_ENERGY_KWH_GA = "35/1/23"
PROJECTOR_CMD_GA = "32/6/2"
PROJECTOR_STATUS_GA = "32/6/3"


def _with_placement(item: dict, *, name: str, tags: list[str] | str) -> dict:
    item.update(placement(name=name, tags=tags))
    return item


def _as_on(value: Any) -> bool | None:
    """Coerce current_state JSON into on/off. None if unknown."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "t", "1", "on"):
            return True
        if lowered in ("false", "f", "0", "off", ""):
            return False
    return bool(value)


def _status_base_name(name: str) -> str:
    return name.replace(" :status", "").strip()


def _object_tagset(obj: Object) -> set[str]:
    return {t.strip().lower() for t in (obj.tags or "").split(",") if t.strip()}


def _is_control_object(obj: Object) -> bool:
    return "control" in _object_tagset(obj)


def _status_sibling_names(obj: Object) -> list[str]:
    """Likely status object names for a control GA (KNX `:status` or BLE `_state`)."""
    name = obj.name or ""
    names = [f"{name} :status"]
    lower = name.lower()
    if lower.endswith("_cmd"):
        stem = name[:-4]
        names.extend([f"{stem}_state", f"{stem}_status"])
    return names


def _feedback_value(
    obj: Object,
    states: dict[str, Any],
    by_name: dict[str, Object],
    by_ga: dict[str, Object],
) -> Any:
    """Value to compare for skip_unchanged. Prefer status sibling over control GA."""
    if not _is_control_object(obj):
        return states.get(obj.ga)
    for cand in _status_sibling_names(obj):
        sibling = by_name.get(cand)
        if sibling is not None:
            return states.get(sibling.ga)
    parts = (obj.ga or "").split("/")
    if len(parts) == 3:
        try:
            alt_ga = f"{parts[0]}/{int(parts[1]) + 1}/{parts[2]}"
        except ValueError:
            alt_ga = ""
        sibling = by_ga.get(alt_ga)
        if (
            sibling is not None
            and "status" in _object_tagset(sibling)
            and "control" not in _object_tagset(sibling)
        ):
            return states.get(sibling.ga)
    return states.get(obj.ga)


async def _light_status_by_control_name(
    session: AsyncSession,
    house_id: str,
    states: dict[str, Any],
) -> dict[str, Any]:
    """Map control object name → status GA value.

    Status objects usually lack floor tags (`2floor`), so this loads all light
    statuses (query=None) and pairs them by name. Wall switches update 1/2/*,
    not 1/1/* — skip_unchanged must use this map, not control state.
    """
    statuses = await resolve_objects(
        session, house_id, query=None, kind=DiscoverKind.LIGHT, role=ObjectRole.LIGHT_STATUS
    )
    return {_status_base_name(s.name): states.get(s.ga) for s in statuses.matches}


def _norm_ga(ga: str) -> str:
    """Normalize GA to slash form used by objects schema (1/2/3).

    MQTT/current_state historically may store dash form (1-2-3).
    """
    from cottage_monitoring.utils.ga import ga_to_slash

    return ga_to_slash(ga)

async def _get_state_map(session: AsyncSession, house_id: str) -> dict[str, Any]:
    if redis_cache.is_connected:
        try:
            cached = await redis_cache.get_all_states(house_id)
            if cached:
                return {_norm_ga(ga): data.get("value") for ga, data in cached.items()}
        except Exception:
            pass

    result = await session.execute(
        select(CurrentState.ga, CurrentState.value).where(CurrentState.house_id == house_id)
    )
    return {_norm_ga(ga): value for ga, value in result.all()}


async def get_house_status(session: AsyncSession, house_id: str) -> dict[str, Any]:
    result = await session.execute(select(House).where(House.house_id == house_id))
    house = result.scalar_one_or_none()
    if house is None:
        raise HTTPException(status_code=404, detail="House not found")

    obj_count = await session.scalar(
        select(func.count()).select_from(Object).where(
            Object.house_id == house_id, Object.is_active.is_(True)
        )
    )
    return {
        "house_id": house.house_id,
        "online_status": house.online_status,
        "last_seen": house.last_seen.isoformat() if house.last_seen else None,
        "is_active": house.is_active,
        "active_object_count": obj_count or 0,
    }


def _appliance_base_name(name: str) -> str:
    lower = name.lower()
    for suffix in ("_cmd", "_state", "_status", "_temp", "_temperature", "_setpoint"):
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _is_kettle_setpoint(obj) -> bool:
    return "setpoint" in obj.name.lower() or "setpoint" in {t.lower() for t in obj.tags}


def _group_appliances(matches: list, states: dict[str, Any]) -> list[dict[str, Any]]:
    """Collapse cmd/state/temp GAs for one BLE/Zigbee appliance into a single summary."""
    groups: dict[str, dict[str, Any]] = {}
    for m in matches:
        base = _appliance_base_name(m.name)
        g = groups.setdefault(
            base,
            {
                "name": base,
                "cmd_ga": None,
                "state_ga": None,
                "temp_ga": None,
                "setpoint_ga": None,
                "on": None,
                "state": None,
                "temp": None,
                "setpoint_c": None,
                "objects": [],
            },
        )
        g["objects"].append({"ga": m.ga, "name": m.name, "tags": m.tags, "role": m.role.value})
        n = m.name.lower()
        tags = {t.lower() for t in m.tags}
        val = states.get(m.ga)
        if "setpoint" in n or "setpoint" in tags:
            g["setpoint_ga"] = m.ga
            g["setpoint_c"] = val
        elif "cmd" in n or ("zigbee_send" in tags and ("control" in tags or "ble" in tags)):
            g["cmd_ga"] = m.ga
            g["_cmd"] = val
        elif "temp" in n or "temp" in tags:
            g["temp_ga"] = m.ga
            g["temp"] = val
        elif "state" in n or "status" in n or "status" in tags:
            g["state_ga"] = m.ga
            g["state"] = val
    for g in groups.values():
        # Physical on/off is state (33/1/38), not cmd (33/1/39) — same split as lights.
        state_on = _as_on(g["state"]) if g["state_ga"] is not None else None
        cmd_on = _as_on(g.pop("_cmd", None)) if g["cmd_ga"] is not None else None
        g["on"] = state_on if state_on is not None else cmd_on
    return list(groups.values())


async def discover(
    session: AsyncSession,
    house_id: str,
    *,
    query: str | None = None,
    kind: str = "all",
) -> dict[str, Any]:
    dk = DiscoverKind(kind)
    result = await resolve_objects(session, house_id, query=query, kind=dk)
    items = [
        {
            "ga": m.ga,
            "name": m.name,
            "role": m.role.value,
            "tags": m.tags,
        }
        for m in result.matches
    ]

    # For appliances (e.g. teapot), return one summary instead of ambiguous cmd/temp/state.
    if dk == DiscoverKind.APPLIANCE and result.matches:
        states = await _get_state_map(session, house_id)
        appliances = _group_appliances(result.matches, states)
        if len(appliances) == 1:
            return {
                "status": "ok",
                "appliance": appliances[0],
                "items": items,
            }
        if len(appliances) > 1:
            return {
                "status": "ambiguous",
                "appliances": appliances,
                "items": items,
            }

    return {
        "status": result.status,
        "items": items,
    }


async def get_temperatures(
    session: AsyncSession,
    house_id: str,
    *,
    query: str | None = None,
) -> dict[str, Any]:
    states = await _get_state_map(session, house_id)
    items: list[dict[str, Any]] = []

    for role, source in (
        (ObjectRole.ROOM_TEMP, "air"),
        (ObjectRole.FLOOR_TEMP, "floor"),
        (ObjectRole.WEATHER, "outdoor"),
    ):
        resolved = await resolve_objects(
            session, house_id, query=query, role=role
        )
        for obj in resolved.matches:
            items.append(
                _with_placement(
                    {
                        "name": obj.name,
                        "ga": obj.ga,
                        "source": source,
                        "value": states.get(obj.ga),
                        "units": "°C" if source != "outdoor" else None,
                    },
                    name=obj.name,
                    tags=obj.tags,
                )
            )

    if not query and not items:
        for role, source in (
            (ObjectRole.ROOM_TEMP, "air"),
            (ObjectRole.FLOOR_TEMP, "floor"),
        ):
            resolved = await resolve_objects(session, house_id, kind=DiscoverKind.TEMP, role=role)
            for obj in resolved.matches:
                items.append(
                    _with_placement(
                        {
                            "name": obj.name,
                            "ga": obj.ga,
                            "source": source,
                            "value": states.get(obj.ga),
                        },
                        name=obj.name,
                        tags=obj.tags,
                    )
                )

    return {"items": items, "total": len(items)}


async def get_sensors(
    session: AsyncSession,
    house_id: str,
    *,
    query: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    states = await _get_state_map(session, house_id)
    if kind == "humidity":
        result = await resolve_objects(
            session,
            house_id,
            query=query,
            kind=DiscoverKind.SENSOR,
            role=ObjectRole.ROOM_HUMIDITY,
        )
    elif kind == "battery":
        result = await resolve_objects(
            session,
            house_id,
            query=query,
            kind=DiscoverKind.SENSOR,
            role=ObjectRole.ROOM_BATTERY,
        )
    else:
        dk = DiscoverKind(kind) if kind else DiscoverKind.SENSOR
        result = await resolve_objects(session, house_id, query=query, kind=dk)
    items = [
        _with_placement(
            {
                "name": m.name,
                "ga": m.ga,
                "role": m.role.value,
                "value": states.get(m.ga),
            },
            name=m.name,
            tags=m.tags,
        )
        for m in result.matches
    ]
    return {"status": result.status, "items": items, "total": len(items)}


async def list_lights(session: AsyncSession, house_id: str, *, query: str | None = None) -> dict:
    states = await _get_state_map(session, house_id)
    controls = await resolve_objects(
        session, house_id, query=query, kind=DiscoverKind.LIGHT, role=ObjectRole.LIGHT_CONTROL
    )
    status_by_base = await _light_status_by_control_name(session, house_id, states)

    items = []
    for c in controls.matches:
        val = status_by_base.get(c.name, states.get(c.ga))
        row = {"name": c.name, "ga": c.ga, "value": val, "on": _as_on(val)}
        zone = params_for_relay(c.ga)
        if zone is not None:
            row["brightness"] = states.get(zone.brightness.status)
            row["color_temp"] = states.get(zone.color_temp.status)
            row["rgb"] = states.get(zone.rgb.status)
        items.append(_with_placement(row, name=c.name, tags=c.tags))
    return {"items": items, "total": len(items)}


async def _resolve_device_and_send(
    session: AsyncSession,
    house_id: str,
    ga: str,
    value: Any,
    *,
    comment: str | None = None,
) -> dict[str, Any]:
    obj_result = await session.execute(
        select(Object).where(Object.house_id == house_id, Object.ga == ga)
    )
    obj = obj_result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=400, detail=f"Unknown GA: {ga}")
    if not obj.device_id:
        raise HTTPException(status_code=400, detail="Cannot resolve device_id")

    payload: dict[str, Any] = {"ga": ga, "value": value}
    if comment:
        payload["comment"] = comment
    cmd = await send_command(house_id, obj.device_id, payload, session=session)
    await session.commit()
    return {
        "request_id": str(cmd.request_id),
        "ga": ga,
        "value": value,
        "status": cmd.status,
    }


def _requested_light_params(
    *,
    brightness: int | None,
    color_temp: int | None,
    rgb: int | None,
) -> dict[str, int]:
    out: dict[str, int] = {}
    if brightness is not None:
        out["brightness"] = brightness
    if color_temp is not None:
        out["color_temp"] = color_temp
    if rgb is not None:
        out["rgb"] = rgb
    return out


def _param_control_items(relay_ga: str, params: dict[str, int]) -> list[dict[str, Any]]:
    zone = params_for_relay(relay_ga)
    if zone is None or not params:
        return []
    items: list[dict[str, Any]] = []
    for name, value in params.items():
        addr = getattr(zone, name)
        items.append({"ga": addr.control, "value": value})
    return items


async def _send_light_batch(
    session: AsyncSession,
    house_id: str,
    *,
    targets: list[tuple[str, str]] | None = None,
    value: Any = None,
    items: list[dict[str, Any]] | None = None,
    comment: str,
) -> dict[str, Any]:
    """Publish one MQTT batch command for multiple GAs on the same device.

    ``items`` may mix bool relay writes and numeric param GAs. When omitted,
    every target is written with the same ``value`` (on/off path).
    """
    if items is None:
        if not targets:
            raise HTTPException(status_code=400, detail="No lights to change")
        items = [{"ga": ga, "value": value} for ga, _name in targets]
    if not items:
        raise HTTPException(status_code=400, detail="No lights to change")

    device_id: str | None = None
    payload_items: list[dict[str, Any]] = []
    for item in items:
        ga = str(item["ga"])
        item_value = item["value"]
        obj_result = await session.execute(
            select(Object).where(Object.house_id == house_id, Object.ga == ga)
        )
        obj = obj_result.scalar_one_or_none()
        if obj is None:
            raise HTTPException(status_code=400, detail=f"Unknown GA: {ga}")
        if not obj.device_id:
            raise HTTPException(status_code=400, detail=f"Cannot resolve device_id for {ga}")
        if device_id is None:
            device_id = obj.device_id
        elif obj.device_id != device_id:
            raise HTTPException(
                status_code=400,
                detail="Lights span multiple devices; narrow the query",
            )
        payload_items.append({"ga": ga, "value": item_value})

    payload: dict[str, Any] = {"items": payload_items, "comment": comment}
    t0 = time.perf_counter()
    cmd = await send_command(house_id, device_id, payload, session=session)
    await session.commit()
    send_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(
        "set_lights_batch_sent",
        house_id=house_id,
        request_id=str(cmd.request_id),
        item_count=len(payload_items),
        send_ms=send_ms,
    )
    return {
        "request_id": str(cmd.request_id),
        "status": cmd.status,
        "item_count": len(payload_items),
        "send_ms": send_ms,
    }


async def set_lights(
    session: AsyncSession,
    house_id: str,
    *,
    query: str,
    on: bool | None = None,
    skip_unchanged: bool = True,
    brightness: int | None = None,
    color_temp: int | None = None,
    rgb: int | None = None,
) -> dict[str, Any]:
    """Turn multiple lights on/off in one MQTT batch (zone queries like «1 этаж»)."""
    params = _requested_light_params(
        brightness=brightness, color_temp=color_temp, rgb=rgb
    )
    write_params = bool(params) and on is not False
    if on is None and not write_params:
        raise HTTPException(
            status_code=400,
            detail="at least one of on, brightness, color_temp, rgb is required",
        )
    relay_on = True if on is None else on

    t0 = time.perf_counter()
    states = await _get_state_map(session, house_id)
    result = await resolve_objects(
        session, house_id, query=query, kind=DiscoverKind.LIGHT, role=ObjectRole.LIGHT_CONTROL
    )
    if not result.matches:
        raise HTTPException(status_code=404, detail=f"No lights found for: {query}")

    if len(result.matches) > 1 and not _is_zone_query(query):
        return {
            "status": "ambiguous",
            "candidates": [{"name": m.name, "ga": m.ga} for m in result.matches],
        }

    status_by_base = await _light_status_by_control_name(session, house_id, states)

    skipped: list[dict[str, Any]] = []
    to_change: list[tuple[str, str]] = []
    batch_items: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    for m in result.matches:
        status_val = status_by_base.get(m.name, states.get(m.ga))
        control_val = states.get(m.ga)
        status_on = _as_on(status_val)
        control_on = _as_on(control_val)
        param_items = _param_control_items(m.ga, params) if write_params else []
        # Skip only if status AND control already match. After a write, control
        # updates first; status lags. Skipping OFF because status is still false
        # would leave the light on (HA click-on then click-off).
        skip_relay = skip_unchanged and status_on == relay_on and control_on == relay_on
        # Params imply power: always include relay ON (cloud may be stale while LM
        # is OFF). zb_light_sync is rising-edge only + color intent exclusive so
        # re-assert ON must not echo stale CCT after RGB.
        if write_params and relay_on:
            skip_relay = False
        # Never skip OFF: cloud current_state can still show both false after a
        # recent ON+params (MQTT status lag) → agent reports "выключил" while
        # relays stay true on LM.
        if relay_on is False:
            skip_relay = False
        if skip_relay and not param_items:
            skipped.append({"name": m.name, "ga": m.ga, "on": status_on})
            continue
        to_change.append((m.ga, m.name))
        # Params before relay so OFF→ON sync sees the new color intent after settle.
        batch_items.extend(param_items)
        if not skip_relay:
            batch_items.append({"ga": m.ga, "value": relay_on})
        entry: dict[str, Any] = {"name": m.name, "ga": m.ga, "on": relay_on}
        if write_params:
            entry.update(params)
        changed.append(entry)

    if not to_change:
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        return {
            "status": "ok",
            "request_id": None,
            "changed": [],
            "skipped": skipped,
            "note": "All matching lights already in target state",
            "elapsed_ms": elapsed_ms,
        }

    if write_params:
        out = await _send_light_batch(
            session,
            house_id,
            items=batch_items,
            comment=f"mcp set_lights {query}",
        )
        changed_out = changed
    else:
        out = await _send_light_batch(
            session,
            house_id,
            targets=to_change,
            value=relay_on,
            comment=f"mcp set_lights {query}",
        )
        changed_out = [{"name": name, "ga": ga, "on": relay_on} for ga, name in to_change]
    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    return {
        "status": out["status"],
        "request_id": out["request_id"],
        "changed": changed_out,
        "skipped": skipped,
        "batch": True,
        "item_count": out["item_count"],
        "send_ms": out["send_ms"],
        "elapsed_ms": elapsed_ms,
    }


async def set_commands(
    session: AsyncSession,
    house_id: str,
    *,
    items: list[dict[str, Any]],
    comment: str | None = None,
    skip_unchanged: bool = True,
) -> dict[str, Any]:
    """Send arbitrary GA/value pairs grouped by device_id in minimal batches."""
    if not items:
        raise HTTPException(status_code=400, detail="items must not be empty")
    validate_batch_size(len(items))

    normalized: list[dict[str, Any]] = []
    for item in items:
        ga = str(item.get("ga", "")).strip()
        if not ga or "value" not in item:
            raise HTTPException(status_code=400, detail="Each item must contain ga and value")
        normalized.append({"ga": ga, "value": item["value"]})

    states = await _get_state_map(session, house_id)
    gas = [i["ga"] for i in normalized]
    objs_result = await session.execute(
        select(Object).where(Object.house_id == house_id, Object.ga.in_(gas))
    )
    objs = {o.ga: o for o in objs_result.scalars().all()}

    sibling_names = [n for o in objs.values() for n in _status_sibling_names(o)]
    by_name: dict[str, Object] = {o.name: o for o in objs.values() if o.name}
    by_ga: dict[str, Object] = dict(objs)
    if sibling_names:
        sib_result = await session.execute(
            select(Object).where(Object.house_id == house_id, Object.name.in_(sibling_names))
        )
        for sib in sib_result.scalars().all():
            if sib.name:
                by_name[sib.name] = sib
            by_ga[sib.ga] = sib

    skipped: list[dict[str, Any]] = []
    by_device: dict[str, list[dict[str, Any]]] = {}
    for item in normalized:
        ga = item["ga"]
        value = item["value"]
        obj = objs.get(ga)
        if obj is None:
            raise HTTPException(status_code=400, detail=f"Unknown GA: {ga}")
        validate_command_value(obj.datatype, value, ga)
        if not obj.device_id:
            raise HTTPException(status_code=400, detail=f"Cannot resolve device_id for {ga}")

        current = _feedback_value(obj, states, by_name, by_ga)
        if skip_unchanged and current is not None and current == value:
            skipped.append({"ga": ga, "value": value, "current": current})
            continue

        by_device.setdefault(obj.device_id, []).append({"ga": ga, "value": value})

    if not by_device:
        return {
            "status": "ok",
            "commands": [],
            "skipped": skipped,
            "note": "All items already in requested state",
        }

    commands: list[dict[str, Any]] = []
    for device_id, device_items in by_device.items():
        payload: dict[str, Any] = {"items": device_items}
        if comment:
            payload["comment"] = comment
        cmd = await send_command(house_id, device_id, payload, session=session)
        commands.append(
            {
                "request_id": str(cmd.request_id),
                "device_id": device_id,
                "item_count": len(device_items),
            }
        )
    await session.commit()
    return {"status": "sent", "commands": commands, "skipped": skipped}


async def set_light(
    session: AsyncSession,
    house_id: str,
    *,
    query: str,
    on: bool | None = None,
    brightness: int | None = None,
    color_temp: int | None = None,
    rgb: int | None = None,
) -> dict[str, Any]:
    result = await resolve_objects(
        session, house_id, query=query, kind=DiscoverKind.LIGHT, role=ObjectRole.LIGHT_CONTROL
    )
    if result.status == "not_found":
        raise HTTPException(status_code=404, detail=f"No light found for: {query}")
    if result.status == "ambiguous":
        return {
            "status": "ambiguous",
            "candidates": [{"name": m.name, "ga": m.ga} for m in result.matches],
        }
    obj = result.single
    if obj is None:
        raise HTTPException(status_code=500, detail="Resolver returned ok without a match")
    params = _requested_light_params(
        brightness=brightness, color_temp=color_temp, rgb=rgb
    )
    write_params = bool(params) and on is not False
    if not write_params:
        if on is None:
            raise HTTPException(
                status_code=400,
                detail="at least one of on, brightness, color_temp, rgb is required",
            )
        return await _resolve_device_and_send(
            session, house_id, obj.ga, on, comment=f"mcp set_light {query}"
        )
    relay_on = True if on is None else on
    items = [*_param_control_items(obj.ga, params), {"ga": obj.ga, "value": relay_on}]
    out = await _send_light_batch(
        session,
        house_id,
        items=items,
        comment=f"mcp set_light {query}",
    )
    return {
        "request_id": out["request_id"],
        "status": out["status"],
        "ga": obj.ga,
        "value": relay_on,
        "item_count": out["item_count"],
        "batch": True,
    }


async def get_climate(
    session: AsyncSession,
    house_id: str,
    *,
    query: str | None = None,
) -> dict[str, Any]:
    states = await _get_state_map(session, house_id)
    auto = states.get(AUTO_HEATING_GA)

    zones: list[dict[str, Any]] = []
    setpoints = await resolve_objects(
        session, house_id, query=query, role=ObjectRole.CLIMATE_SETPOINT
    )
    for sp in setpoints.matches:
        room_query = sp.name.replace("Уставка ТП -", "").replace("Уставка ТП - ", "").strip()
        floor = await resolve_objects(session, house_id, query=room_query, role=ObjectRole.FLOOR_TEMP)
        room = await resolve_objects(session, house_id, query=room_query, role=ObjectRole.ROOM_TEMP)
        relay = await resolve_objects(session, house_id, query=room_query, role=ObjectRole.HEAT_RELAY_STATUS)
        place = placement(name=sp.name, tags=sp.tags)
        zone = {
            "room": room_query,
            "setpoint_ga": sp.ga,
            "setpoint": states.get(sp.ga),
            "floor_temp": states.get(floor.matches[0].ga) if floor.matches else None,
            "room_temp": states.get(room.matches[0].ga) if room.matches else None,
            "relay_on": states.get(relay.matches[0].ga) if relay.matches else None,
        }
        zone.update(place)
        zones.append(zone)

    return {
        "auto_heating_enabled": auto,
        "note": (
            "Setpoint alone does not turn on floor heating; relays are managed by the auto "
            "balancing algorithm (1/7/1). Manual relay control is debug-only."
        ),
        "zones": zones,
    }


async def set_auto_heating(
    session: AsyncSession,
    house_id: str,
    *,
    on: bool,
) -> dict[str, Any]:
    return await _resolve_device_and_send(
        session, house_id, AUTO_HEATING_GA, on, comment="mcp set_auto_heating"
    )


async def set_climate_setpoint(
    session: AsyncSession,
    house_id: str,
    *,
    query: str | None = None,
    setpoint_c: float,
    force_relay: bool | None = None,
    ga: str | None = None,
) -> dict[str, Any]:
    if ga:
        obj_result = await session.execute(
            select(Object).where(
                Object.house_id == house_id,
                Object.ga == ga,
                Object.is_active.is_(True),
            )
        )
        obj = obj_result.scalar_one_or_none()
        if obj is None:
            raise HTTPException(status_code=404, detail=f"No setpoint found for GA: {ga}")
        role = classify_object(obj)
        if role != ObjectRole.CLIMATE_SETPOINT and not ga.startswith("1/6/"):
            raise HTTPException(status_code=400, detail=f"GA {ga} is not a climate setpoint")
        out = await _resolve_device_and_send(
            session, house_id, ga, setpoint_c, comment=f"mcp set_climate {query or ga}"
        )
    else:
        result = await resolve_objects(
            session,
            house_id,
            query=query,
            kind=DiscoverKind.CLIMATE,
            role=ObjectRole.CLIMATE_SETPOINT,
        )
        if result.status == "not_found":
            raise HTTPException(status_code=404, detail=f"No setpoint found for: {query}")
        if result.status == "ambiguous":
            candidates = [{"name": m.name, "ga": m.ga} for m in result.matches]
            logger.warning("set_climate_ambiguous", query=query, candidates=candidates)
            return {
                "status": "ambiguous",
                "candidates": candidates,
            }
        resolved = result.single
        if resolved is None:
            raise HTTPException(status_code=500, detail="Resolver returned ok without a match")
        out = await _resolve_device_and_send(
            session, house_id, resolved.ga, setpoint_c, comment=f"mcp set_climate {query}"
        )
    out["note"] = "Setpoint updated; relay state is controlled by auto algorithm unless force_relay is used."

    if force_relay is not None and query:
        relay_result = await resolve_objects(
            session, house_id, query=query, role=ObjectRole.HEAT_RELAY_CONTROL
        )
        if relay_result.single:
            relay_out = await _resolve_device_and_send(
                session,
                house_id,
                relay_result.single.ga,
                force_relay,
                comment="mcp debug force_relay",
            )
            out["relay"] = relay_out
            out["warning"] = "Manual relay control is debug-only; auto algorithm normally manages relays."
    return out


async def get_energy_status(session: AsyncSession, house_id: str) -> dict[str, Any]:
    states = await _get_state_map(session, house_id)
    result = await session.execute(
        select(Object).where(
            Object.house_id == house_id,
            Object.is_active.is_(True),
            Object.ga.in_(ENERGY_SUMMARY_GAS),
        )
    )
    objs = {o.ga: o for o in result.scalars().all()}
    items = []
    for ga in ENERGY_SUMMARY_GAS:
        obj = objs.get(ga)
        if not obj:
            continue
        items.append(
            {
                "ga": ga,
                "name": obj.name,
                "units": obj.units,
                "value": states.get(ga),
            }
        )
    return {"items": items, "total": len(items)}


async def get_heating_diagnostics(session: AsyncSession, house_id: str) -> dict[str, Any]:
    states = await _get_state_map(session, house_id)
    result = await session.execute(
        select(Object).where(
            Object.house_id == house_id,
            Object.is_active.is_(True),
            Object.ga.in_(HEATING_DIAG_GAS + [AUTO_HEATING_GA]),
        )
    )
    items = []
    for obj in result.scalars().all():
        items.append(
            {
                "ga": obj.ga,
                "name": obj.name,
                "value": states.get(obj.ga),
            }
        )
    return {
        "items": items,
        "interpretation": {
            "34/1/1": "zigbee/fallback/on zone counts",
            "34/1/2": "overheat/long_block protection counts",
            "34/1/3": "outdoor temp and weather k_base",
            "34/1/4": "floor power using/limit watts",
            "1/7/1": "auto balancing algorithm enabled",
        },
    }


async def set_kettle(
    session: AsyncSession,
    house_id: str,
    *,
    on: bool | None = None,
    setpoint_c: float | None = None,
) -> dict[str, Any]:
    """Control BLE teapot — cmd and/or setpoint. Never write °C to cmd 33/1/39."""
    matches: list = []
    for query in ("teapot", "ble_teapot", "чайник", "kettle"):
        result = await resolve_objects(
            session, house_id, query=query, kind=DiscoverKind.APPLIANCE
        )
        if result.matches:
            matches = list(result.matches)
            break

    out: dict[str, Any] = {}

    if setpoint_c is not None:
        setpoints = [m for m in matches if _is_kettle_setpoint(m)]
        if len(setpoints) != 1:
            raise HTTPException(
                status_code=404, detail="Kettle setpoint object not found"
            )
        out["setpoint"] = await _resolve_device_and_send(
            session,
            house_id,
            setpoints[0].ga,
            setpoint_c,
            comment="mcp set_kettle setpoint",
        )

    if on is not None:
        cmds = [
            m
            for m in matches
            if not _is_kettle_setpoint(m)
            and (
                "cmd" in m.name.lower()
                or ("control" in m.tags and "zigbee_send" in m.tags)
            )
        ]
        if len(cmds) == 1:
            cmd_result = await _resolve_device_and_send(
                session, house_id, cmds[0].ga, on, comment="mcp set_kettle"
            )
            if not out:
                return cmd_result
            out["cmd"] = cmd_result
            return out
        if len(cmds) > 1:
            return {
                "status": "ambiguous",
                "candidates": [{"name": m.name, "ga": m.ga} for m in cmds],
                **out,
            }

        obj_result = await session.execute(
            select(Object).where(Object.house_id == house_id, Object.ga == "33/1/39")
        )
        obj = obj_result.scalar_one_or_none()
        if obj:
            cmd_result = await _resolve_device_and_send(
                session, house_id, "33/1/39", on, comment="mcp set_kettle"
            )
            if not out:
                return cmd_result
            out["cmd"] = cmd_result
            return out
        if out:
            raise HTTPException(
                status_code=404,
                detail={"error": "Kettle control object not found", **out},
            )
        raise HTTPException(status_code=404, detail="Kettle control object not found")

    return out


async def get_kettle(session: AsyncSession, house_id: str) -> dict[str, Any]:
    states = await _get_state_map(session, house_id)
    result = await resolve_objects(session, house_id, query="teapot", kind=DiscoverKind.APPLIANCE)
    if not result.matches:
        for query in ("чайник", "kettle", "ble_teapot"):
            result = await resolve_objects(
                session, house_id, query=query, kind=DiscoverKind.APPLIANCE
            )
            if result.matches:
                break
    appliances = _group_appliances(result.matches, states)
    if len(appliances) == 1:
        first = result.matches[0] if result.matches else None
        if first is not None:
            appliances[0].update(placement(name=first.name, tags=first.tags))
            appliances[0].update(placement(name=appliances[0]["name"], tags=first.tags))
        return {"status": "ok", "appliance": appliances[0]}
    if len(appliances) > 1:
        return {"status": "ambiguous", "appliances": appliances}
    return {"status": "not_found", "appliance": None}


async def get_ai_srv_switcher(session: AsyncSession, house_id: str) -> dict[str, Any]:
    """Read AI-SRV wall-plug relay + electrical metrics for HA ИТ dashboard."""
    states = await _get_state_map(session, house_id)
    status_on = _as_on(states.get(AI_SRV_SWITCHER_STATUS_GA))
    if status_on is None:
        status_on = _as_on(states.get(AI_SRV_SWITCHER_CMD_GA))
    return {
        "on": status_on,
        "power_w": states.get(AI_SRV_PLUG_POWER_W_GA),
        "current_a": states.get(AI_SRV_PLUG_CURRENT_A_GA),
        "voltage_v": states.get(AI_SRV_PLUG_VOLTAGE_V_GA),
        "energy_kwh": states.get(AI_SRV_PLUG_ENERGY_KWH_GA),
        "cmd_ga": AI_SRV_SWITCHER_CMD_GA,
        "status_ga": AI_SRV_SWITCHER_STATUS_GA,
    }


async def set_ai_srv_switcher(
    session: AsyncSession,
    house_id: str,
    *,
    on: bool,
) -> dict[str, Any]:
    """Toggle AI-SRV Zigbee plug (cmd 32/6/5)."""
    return await _resolve_device_and_send(
        session,
        house_id,
        AI_SRV_SWITCHER_CMD_GA,
        on,
        comment="mcp set_ai_srv_switcher",
    )


async def get_projector(session: AsyncSession, house_id: str) -> dict[str, Any]:
    """Read movie projector Zigbee relay status for HA ИТ dashboard."""
    states = await _get_state_map(session, house_id)
    status_on = _as_on(states.get(PROJECTOR_STATUS_GA))
    if status_on is None:
        status_on = _as_on(states.get(PROJECTOR_CMD_GA))
    return {
        "on": status_on,
        "cmd_ga": PROJECTOR_CMD_GA,
        "status_ga": PROJECTOR_STATUS_GA,
    }


async def set_projector(
    session: AsyncSession,
    house_id: str,
    *,
    on: bool,
) -> dict[str, Any]:
    """Toggle movie projector Zigbee relay (cmd 32/6/2)."""
    return await _resolve_device_and_send(
        session,
        house_id,
        PROJECTOR_CMD_GA,
        on,
        comment="mcp set_projector",
    )


async def get_command_status(
    session: AsyncSession,
    house_id: str,
    request_id: str,
) -> dict[str, Any]:
    try:
        rid = uuid.UUID(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid request_id") from exc

    result = await session.execute(
        select(Command).where(Command.house_id == house_id, Command.request_id == rid)
    )
    cmd = result.scalar_one_or_none()
    if cmd is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return {
        "request_id": str(cmd.request_id),
        "status": cmd.status,
        "ts_sent": cmd.ts_sent.isoformat() if cmd.ts_sent else None,
        "ts_ack": cmd.ts_ack.isoformat() if cmd.ts_ack else None,
        "results": cmd.results,
    }


_inmem_write_rate: dict[Any, list[float]] = {}


def _inmem_rate_check(key_id: Any, limit: int) -> None:
    """Fail-closed sliding-window limiter used when Redis is unavailable."""
    now = time.monotonic()
    bucket = _inmem_write_rate.setdefault(key_id, [])
    cutoff = now - 60
    bucket[:] = [ts for ts in bucket if ts > cutoff]
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Write rate limit exceeded")
    bucket.append(now)


async def check_write_rate_limit(ctx: ApiKeyContext) -> None:
    from cottage_monitoring.config import settings
    from cottage_monitoring.deps import redis_cache

    limit = settings.mcp_write_rate_limit_per_minute
    if redis_cache.is_connected:
        try:
            key = f"mcp:write_rate:{ctx.key_id}"
            count = await redis_cache.incr_with_ttl(key, 60)
            if count > limit:
                raise HTTPException(status_code=429, detail="Write rate limit exceeded")
            return
        except HTTPException:
            raise
        except Exception:
            # Redis error mid-flight → fall back to in-memory rather than fail-open.
            pass
    _inmem_rate_check(ctx.key_id, limit)
