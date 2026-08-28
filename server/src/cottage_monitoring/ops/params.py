"""Parameter models for Ops — one per operation, shared by both faces.

``house_id`` is deliberately absent: the face resolves it (path segment on REST,
optional tool argument on MCP), never the body. ``extra="forbid"`` makes a body
that tries to smuggle it fail with 422 instead of being silently ignored.

Field names, types and defaults mirror the MCP tool arguments as they were
before the registry, so tool JSON Schema stays byte-for-byte compatible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

if TYPE_CHECKING:
    from cottage_monitoring.ops.spec import OpSpec


class OpParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


def validate_params(spec: OpSpec, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Turn raw arguments into handler kwargs, defaults filled, on both faces.

    Raises HTTPException 422 so the REST face answers with its usual error body
    and the MCP face maps it to the same JSON error contract as everything else.
    """
    if spec.params_model is None:
        if raw:
            raise HTTPException(
                status_code=422, detail=f"Op '{spec.name}' takes no parameters"
            )
        return {}

    try:
        parsed = spec.params_model.model_validate(raw or {})
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
                for err in exc.errors(include_url=False)
            ],
        ) from exc
    return parsed.model_dump()


class NoParams(OpParams):
    """Ops that take nothing beyond session and house."""


class QueryParams(OpParams):
    query: str = ""


class DiscoverParams(OpParams):
    query: str = ""
    kind: str = "all"


class GetSensorsParams(OpParams):
    query: str = ""
    kind: str = "sensor"


class SetLightParams(OpParams):
    query: str
    on: bool


class SetLightsParams(OpParams):
    query: str
    on: bool
    skip_unchanged: bool = True


class SetCommandsParams(OpParams):
    items: list[dict[str, Any]]
    comment: str = ""
    skip_unchanged: bool = True


class SetClimateParams(OpParams):
    query: str
    setpoint_c: float
    force_relay: bool | None = None


class SetAutoHeatingParams(OpParams):
    on: bool


class SetKettleParams(OpParams):
    on: bool | None = None
    setpoint_c: float | None = None

    @model_validator(mode="after")
    def on_or_setpoint(self) -> SetKettleParams:
        if self.on is None and self.setpoint_c is None:
            raise ValueError("either on or setpoint_c is required")
        if self.setpoint_c is not None and not (40 <= self.setpoint_c <= 100):
            raise ValueError("setpoint_c must be between 40 and 100")
        return self


class GetCommandStatusParams(OpParams):
    request_id: str
