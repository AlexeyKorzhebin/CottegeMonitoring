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
from cottage_monitoring.services.command_service import send_command
from cottage_monitoring.services.object_resolver import (
    AUTO_HEATING_GA,
    ENERGY_SUMMARY_GAS,
    HEATING_DIAG_GAS,
    DiscoverKind,
    ObjectRole,
    _is_zone_query,
    resolve_objects,
)

logger = structlog.get_logger(__name__)

def _norm_ga(ga: str) -> str:
    """Normalize GA to slash form used by objects schema (1/2/3).

    MQTT/current_state historically may store dash form (1-2-3).
    """
    return ga.replace("-", "/")


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
    for suffix in ("_cmd", "_state", "_status", "_temp", "_temperature"):
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return name


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
                "on": None,
                "state": None,
                "temp": None,
                "objects": [],
            },
        )
        g["objects"].append({"ga": m.ga, "name": m.name, "tags": m.tags, "role": m.role.value})
        n = m.name.lower()
        tags = {t.lower() for t in m.tags}
        val = states.get(m.ga)
        if "cmd" in n or ("zigbee_send" in tags and ("control" in tags or "ble" in tags)):
            g["cmd_ga"] = m.ga
            g["on"] = val
        elif "temp" in n or "temp" in tags:
            g["temp_ga"] = m.ga
            g["temp"] = val
        elif "state" in n or "status" in n or "status" in tags:
            g["state_ga"] = m.ga
            g["state"] = val
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
                {
                    "name": obj.name,
                    "ga": obj.ga,
                    "source": source,
                    "value": states.get(obj.ga),
                    "units": "°C" if source != "outdoor" else None,
                }
            )

    if not query and not items:
        for role, source in (
            (ObjectRole.ROOM_TEMP, "air"),
            (ObjectRole.FLOOR_TEMP, "floor"),
        ):
            resolved = await resolve_objects(session, house_id, kind=DiscoverKind.TEMP, role=role)
            for obj in resolved.matches:
                items.append(
                    {
                        "name": obj.name,
                        "ga": obj.ga,
                        "source": source,
                        "value": states.get(obj.ga),
                    }
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
    dk = DiscoverKind(kind) if kind else DiscoverKind.SENSOR
    result = await resolve_objects(session, house_id, query=query, kind=dk)
    items = [
        {
            "name": m.name,
            "ga": m.ga,
            "role": m.role.value,
            "value": states.get(m.ga),
        }
        for m in result.matches
    ]
    return {"status": result.status, "items": items, "total": len(items)}


async def list_lights(session: AsyncSession, house_id: str, *, query: str | None = None) -> dict:
    states = await _get_state_map(session, house_id)
    controls = await resolve_objects(
        session, house_id, query=query, kind=DiscoverKind.LIGHT, role=ObjectRole.LIGHT_CONTROL
    )
    statuses = await resolve_objects(
        session, house_id, query=query, kind=DiscoverKind.LIGHT, role=ObjectRole.LIGHT_STATUS
    )
    status_by_base = {}
    for s in statuses.matches:
        base = s.name.replace(" :status", "").strip()
        status_by_base[base] = states.get(s.ga)

    items = []
    for c in controls.matches:
        val = status_by_base.get(c.name, states.get(c.ga))
        items.append({"name": c.name, "ga": c.ga, "value": val, "on": bool(val) if val is not None else None})
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


async def _send_light_batch(
    session: AsyncSession,
    house_id: str,
    *,
    targets: list[tuple[str, str]],
    value: bool,
    comment: str,
) -> dict[str, Any]:
    """Publish one MQTT batch command for multiple GAs on the same device."""
    if not targets:
        raise HTTPException(status_code=400, detail="No lights to change")

    device_id: str | None = None
    items: list[dict[str, Any]] = []
    for ga, _name in targets:
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
        items.append({"ga": ga, "value": value})

    payload: dict[str, Any] = {"items": items, "comment": comment}
    t0 = time.perf_counter()
    cmd = await send_command(house_id, device_id, payload, session=session)
    await session.commit()
    send_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(
        "set_lights_batch_sent",
        house_id=house_id,
        request_id=str(cmd.request_id),
        item_count=len(items),
        send_ms=send_ms,
    )
    return {
        "request_id": str(cmd.request_id),
        "status": cmd.status,
        "item_count": len(items),
        "send_ms": send_ms,
    }


async def set_lights(
    session: AsyncSession,
    house_id: str,
    *,
    query: str,
    on: bool,
    skip_unchanged: bool = True,
) -> dict[str, Any]:
    """Turn multiple lights on/off in one MQTT batch (zone queries like «1 этаж»)."""
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

    skipped: list[dict[str, Any]] = []
    to_change: list[tuple[str, str]] = []
    for m in result.matches:
        current = states.get(m.ga)
        current_on = bool(current) if current is not None else None
        if skip_unchanged and current_on is not None and current_on == on:
            skipped.append({"name": m.name, "ga": m.ga, "on": current_on})
            continue
        to_change.append((m.ga, m.name))

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

    out = await _send_light_batch(
        session,
        house_id,
        targets=to_change,
        value=on,
        comment=f"mcp set_lights {query}",
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    return {
        "status": out["status"],
        "request_id": out["request_id"],
        "changed": [{"name": name, "ga": ga, "on": on} for ga, name in to_change],
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

    skipped: list[dict[str, Any]] = []
    by_device: dict[str, list[dict[str, Any]]] = {}
    for item in normalized:
        ga = item["ga"]
        value = item["value"]
        obj = objs.get(ga)
        if obj is None:
            raise HTTPException(status_code=400, detail=f"Unknown GA: {ga}")
        if not obj.device_id:
            raise HTTPException(status_code=400, detail=f"Cannot resolve device_id for {ga}")

        current = states.get(ga)
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
    on: bool,
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
    return await _resolve_device_and_send(session, house_id, obj.ga, on, comment=f"mcp set_light {query}")


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
        zones.append(
            {
                "room": room_query,
                "setpoint_ga": sp.ga,
                "setpoint": states.get(sp.ga),
                "floor_temp": states.get(floor.matches[0].ga) if floor.matches else None,
                "room_temp": states.get(room.matches[0].ga) if room.matches else None,
                "relay_on": states.get(relay.matches[0].ga) if relay.matches else None,
            }
        )

    return {
        "auto_heating_enabled": auto,
        "note": (
            "Setpoint alone does not turn on floor heating; relays are managed by the auto "
            "balancing algorithm (1/7/1). Manual relay control is debug-only."
        ),
        "zones": zones,
    }


async def set_climate_setpoint(
    session: AsyncSession,
    house_id: str,
    *,
    query: str,
    setpoint_c: float,
    force_relay: bool | None = None,
) -> dict[str, Any]:
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
        return {
            "status": "ambiguous",
            "candidates": [{"name": m.name, "ga": m.ga} for m in result.matches],
        }
    obj = result.single
    if obj is None:
        raise HTTPException(status_code=500, detail="Resolver returned ok without a match")
    out = await _resolve_device_and_send(
        session, house_id, obj.ga, setpoint_c, comment=f"mcp set_climate {query}"
    )
    out["note"] = "Setpoint updated; relay state is controlled by auto algorithm unless force_relay is used."

    if force_relay is not None:
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
    on: bool,
) -> dict[str, Any]:
    """Control BLE teapot — write to cmd GA (33/1/39: ble, control, zigbee_send)."""
    for query in ("teapot", "ble_teapot", "чайник", "kettle"):
        result = await resolve_objects(
            session, house_id, query=query, kind=DiscoverKind.APPLIANCE
        )
        cmds = [
            m
            for m in result.matches
            if "cmd" in m.name.lower()
            or ("control" in m.tags and "zigbee_send" in m.tags)
        ]
        if len(cmds) == 1:
            return await _resolve_device_and_send(
                session, house_id, cmds[0].ga, on, comment="mcp set_kettle"
            )
        if len(cmds) > 1:
            return {
                "status": "ambiguous",
                "candidates": [{"name": m.name, "ga": m.ga} for m in cmds],
            }

    obj_result = await session.execute(
        select(Object).where(Object.house_id == house_id, Object.ga == "33/1/39")
    )
    obj = obj_result.scalar_one_or_none()
    if obj:
        return await _resolve_device_and_send(
            session, house_id, "33/1/39", on, comment="mcp set_kettle"
        )
    raise HTTPException(status_code=404, detail="Kettle control object not found")


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
        return {"status": "ok", "appliance": appliances[0]}
    if len(appliances) > 1:
        return {"status": "ambiguous", "appliances": appliances}
    return {"status": "not_found", "appliance": None}


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


async def check_write_rate_limit(ctx: ApiKeyContext) -> None:
    from cottage_monitoring.config import settings
    from cottage_monitoring.deps import redis_cache

    if not redis_cache.is_connected:
        return
    key = f"mcp:write_rate:{ctx.key_id}"
    count = await redis_cache.incr_with_ttl(key, 60)
    if count > settings.mcp_write_rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Write rate limit exceeded")
