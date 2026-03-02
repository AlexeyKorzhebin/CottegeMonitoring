"""Schemas API: list versions, get detail, diff between versions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cottage_monitoring.db.session import get_session
from cottage_monitoring.models.house import House
from cottage_monitoring.models.schema_version import SchemaVersion

router = APIRouter()

# Object fields to compare in diff (from raw_meta_json)
_OBJECT_FIELDS = ("id", "address", "name", "datatype", "units", "tags", "comment")


def _get_objects_by_ga(raw_meta: dict) -> dict[str, dict]:
    """Extract objects from raw_meta_json keyed by GA (address)."""
    objects = raw_meta.get("objects", [])
    return {str(obj.get("address", "")): obj for obj in objects if obj.get("address")}


def _compute_diff(from_objs: dict[str, dict], to_objs: dict[str, dict]) -> dict:
    """Compute added, removed, changed by GA."""
    from_gas = set(from_objs)
    to_gas = set(to_objs)

    added = [
        {"ga": ga, "name": to_objs[ga].get("name", "")}
        for ga in sorted(to_gas - from_gas)
    ]
    removed = [
        {"ga": ga, "name": from_objs[ga].get("name", "")}
        for ga in sorted(from_gas - to_gas)
    ]

    changed = []
    for ga in sorted(from_gas & to_gas):
        fo = from_objs[ga]
        to = to_objs[ga]
        for field in _OBJECT_FIELDS:
            if field == "address":
                continue
            old_val = fo.get(field)
            new_val = to.get(field)
            if old_val != new_val:
                changed.append({
                    "ga": ga,
                    "field": field,
                    "old": old_val,
                    "new": new_val,
                })

    return {"added": added, "removed": removed, "changed": changed}


@router.get("/houses/{house_id}/schemas")
async def list_schema_versions(
    house_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """List schema versions for a house."""
    # Ensure house exists
    result = await session.execute(select(House).where(House.house_id == house_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="House not found")

    result = await session.execute(
        select(SchemaVersion)
        .where(SchemaVersion.house_id == house_id)
        .order_by(SchemaVersion.ts.desc())
    )
    versions = result.scalars().all()

    # Latest by ts is current
    latest_ts = versions[0].ts if versions else None

    items = [
        {
            "house_id": sv.house_id,
            "schema_hash": sv.schema_hash,
            "ts": sv.ts.isoformat() if sv.ts else None,
            "count": sv.count,
            "is_current": sv.ts == latest_ts if latest_ts else False,
        }
        for sv in versions
    ]

    return {"items": items, "total": len(items)}


@router.get("/houses/{house_id}/schemas/diff")
async def schema_diff(
    house_id: str,
    from_hash: str = Query(..., alias="from", description="Source schema hash"),
    to_hash: str = Query(..., alias="to", description="Target schema hash"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Diff between two schema versions by GA."""
    result = await session.execute(
        select(SchemaVersion).where(
            SchemaVersion.house_id == house_id,
            SchemaVersion.schema_hash.in_([from_hash, to_hash]),
        )
    )
    versions = {sv.schema_hash: sv for sv in result.scalars().all()}

    if from_hash not in versions:
        raise HTTPException(
            status_code=404, detail=f"Schema version not found: {from_hash}"
        )
    if to_hash not in versions:
        raise HTTPException(
            status_code=404, detail=f"Schema version not found: {to_hash}"
        )

    from_objs = _get_objects_by_ga(versions[from_hash].raw_meta_json)
    to_objs = _get_objects_by_ga(versions[to_hash].raw_meta_json)

    diff = _compute_diff(from_objs, to_objs)
    return {
        "from_hash": from_hash,
        "to_hash": to_hash,
        "added": diff["added"],
        "removed": diff["removed"],
        "changed": diff["changed"],
    }


@router.get("/houses/{house_id}/schemas/{schema_hash}")
async def get_schema_detail(
    house_id: str,
    schema_hash: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Schema detail with objects from raw_meta_json."""
    result = await session.execute(
        select(SchemaVersion).where(
            SchemaVersion.house_id == house_id,
            SchemaVersion.schema_hash == schema_hash,
        )
    )
    sv = result.scalar_one_or_none()
    if not sv:
        raise HTTPException(status_code=404, detail="Schema version not found")

    objects = sv.raw_meta_json.get("objects", [])
    return {
        "house_id": sv.house_id,
        "schema_hash": sv.schema_hash,
        "ts": sv.ts.isoformat() if sv.ts else None,
        "count": sv.count,
        "objects": objects,
    }
