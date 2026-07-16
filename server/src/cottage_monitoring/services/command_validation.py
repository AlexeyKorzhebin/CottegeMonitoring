"""Validate command values before publishing to the KNX bus.

Conservative, defence-in-depth checks: reject structurally invalid values and
enforce boolean range for boolean datapoints. We intentionally do NOT force a
numeric type on non-boolean GAs, since the installation may legitimately use
string/scene datapoints — the controller decodes per DPT and rejects mismatches.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

# Max GA/value pairs accepted in a single command batch (DoS guard).
MAX_BATCH_ITEMS = 100

# KNX boolean major datatypes used in this installation (DPT 1.x).
_BOOL_DTYPES = {1, 1001}


def _is_boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and value in (0, 1):
        return True
    if isinstance(value, str) and value.strip().lower() in ("0", "1", "true", "false", "on", "off"):
        return True
    return False


def validate_command_value(datatype: int | None, value: Any, ga: str) -> None:
    """Raise HTTPException(400) if value is structurally invalid for the GA."""
    if value is None:
        raise HTTPException(status_code=400, detail=f"Missing value for GA {ga}")
    if isinstance(value, (dict, list)):
        raise HTTPException(
            status_code=400, detail=f"Invalid value type for GA {ga} (expected scalar)"
        )
    if (datatype or 0) in _BOOL_DTYPES and not _is_boolish(value):
        raise HTTPException(
            status_code=400,
            detail=f"GA {ga} is boolean (DPT{datatype}); value must be 0/1/true/false",
        )


def validate_batch_size(count: int) -> None:
    if count > MAX_BATCH_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Command batch too large: {count} > {MAX_BATCH_ITEMS}",
        )
