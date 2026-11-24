"""Ceiling Zigbee light param GA map (brightness / color_temp / rgb).

Source of truth: ``cm-client/scripts/zb_ceiling_light_catalog.json``.
Do not invent a second GA table.

Load order (first existing file wins):

1. ``CEILING_LIGHT_CATALOG_PATH`` — tests and explicit overrides.
2. Repo checkout: walk parents of this file for
   ``cm-client/scripts/zb_ceiling_light_catalog.json`` (dev / pytest).
3. Packaged snapshot ``cottage_monitoring/data/zb_ceiling_light_catalog.json``.
   Docker builds from ``server/`` (``COPY src/`` then ``pip install .``);
   cm-client is not in the image, so the snapshot must ship as package data.

Keep the snapshot byte-identical to the cm-client file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_CATALOG_NAME = "zb_ceiling_light_catalog.json"
_ENV_PATH = "CEILING_LIGHT_CATALOG_PATH"
_PACKAGED = Path(__file__).resolve().parent.parent / "data" / _CATALOG_NAME


@dataclass(frozen=True)
class ParamAddresses:
    control: str
    status: str


@dataclass(frozen=True)
class CeilingLightZone:
    zone: str
    relay_ga: str
    brightness: ParamAddresses
    color_temp: ParamAddresses
    rgb: ParamAddresses


def catalog_path() -> Path:
    return _resolve_catalog_path()


def load_catalog_rows() -> list[dict[str, Any]]:
    path = _resolve_catalog_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Ceiling light catalog must be a JSON array: {path}")
    return data


def params_for_relay(relay_ga: str) -> CeilingLightZone | None:
    return _zones_by_relay().get(relay_ga)


def _resolve_catalog_path() -> Path:
    env = os.environ.get(_ENV_PATH)
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "cm-client" / "scripts" / _CATALOG_NAME
        if candidate.is_file():
            return candidate
    if _PACKAGED.is_file():
        return _PACKAGED
    raise FileNotFoundError(
        f"Ceiling light catalog {_CATALOG_NAME} not found "
        "(set CEILING_LIGHT_CATALOG_PATH, run from the git checkout, "
        "or ship cottage_monitoring/data/ snapshot for Docker)"
    )


@lru_cache(maxsize=1)
def _zones_by_relay() -> dict[str, CeilingLightZone]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in load_catalog_rows():
        relay = str(row["relay_ga"])
        bucket = grouped.setdefault(
            relay,
            {"zone": row["zone"], "relay_ga": relay, "params": {}},
        )
        param = str(row["param"])
        role = str(row["role"])
        addrs: dict[str, str] = bucket["params"].setdefault(param, {})
        addrs[role] = str(row["ga"])

    out: dict[str, CeilingLightZone] = {}
    for relay, data in grouped.items():
        params = data["params"]
        out[relay] = CeilingLightZone(
            zone=str(data["zone"]),
            relay_ga=relay,
            brightness=_param_pair(params, "brightness"),
            color_temp=_param_pair(params, "color_temp"),
            rgb=_param_pair(params, "rgb"),
        )
    return out


def _param_pair(params: dict[str, dict[str, str]], name: str) -> ParamAddresses:
    addrs = params.get(name) or {}
    control = addrs.get("control")
    status = addrs.get("status")
    if not control or not status:
        raise ValueError(f"Catalog missing {name} control/status pair")
    return ParamAddresses(control=control, status=status)
