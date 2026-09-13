from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
CATALOG_PATH = _REPO / "cm-client" / "scripts" / "ai_srv_catalog.json"

SENTINEL_NUM = -1.0
UNKNOWN = "unknown"
NONE = "none"

_OFFLINE_NUMERIC = (
    "35/1/2",
    "35/1/3",
    "35/1/4",
    "35/1/7",
    "35/1/8",
    "35/1/9",
    "35/1/10",
    "35/1/11",
    "35/1/12",
    "35/1/13",
    "35/1/18",
)


def load_catalog() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def numeric_or_sentinel(value, status=None) -> float:
    if status is not None and status != "fresh":
        return SENTINEL_NUM
    if value is None:
        return SENTINEL_NUM
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return SENTINEL_NUM
    return float(value)


def sensor_loss_or_sentinel(value) -> float:
    if value is None:
        return 0.0
    return numeric_or_sentinel(value, "fresh")


def mib_to_gib(value, status=None) -> float:
    n = numeric_or_sentinel(value, status)
    if n < 0:
        return SENTINEL_NUM
    return n / 1024.0


def bytes_to_gib(value, status=None) -> float:
    n = numeric_or_sentinel(value, status)
    if n < 0:
        return SENTINEL_NUM
    return n / 1073741824.0


def text_or_unknown(value) -> str:
    if value is None or value == "":
        return UNKNOWN
    return str(value)


def shutdown_text(reason_obj, key: str) -> str:
    if not isinstance(reason_obj, dict):
        return NONE
    v = reason_obj.get(key)
    if v is None or v == "":
        return NONE
    return str(v)


def shutdown_temp(reason_obj) -> float:
    if not isinstance(reason_obj, dict):
        return SENTINEL_NUM
    return numeric_or_sentinel(reason_obj.get("last_temperature_c"), "fresh")


def availability_online(payload) -> bool:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "replace")
    return str(payload).strip() == "online"


def offline_numeric_gas() -> list[str]:
    return list(_OFFLINE_NUMERIC)
