"""Parameter models for Ops — one per operation, shared by both faces.

``house_id`` is deliberately absent: the face resolves it (path segment on REST,
optional tool argument on MCP), never the body. ``extra="forbid"`` makes a body
that tries to smuggle it fail with 422 instead of being silently ignored.

Field names, types and defaults mirror the MCP tool arguments as they were
before the registry, so tool JSON Schema stays byte-for-byte compatible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

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


class _LightWrite(Protocol):
    on: bool | None
    brightness: int | None
    color_temp: int | None
    rgb: int | None


def _require_light_on_or_params[T: _LightWrite](model: T) -> T:
    """on is optional when any param is set; at least one of on/params is required."""
    if (
        model.on is None
        and model.brightness is None
        and model.color_temp is None
        and model.rgb is None
    ):
        raise ValueError("at least one of on, brightness, color_temp, rgb is required")
    if model.brightness is not None and not (0 <= model.brightness <= 100):
        raise ValueError("brightness must be between 0 and 100")
    if model.color_temp is not None and model.color_temp < 0:
        raise ValueError("color_temp must be >= 0 (mired)")
    if model.rgb is not None and not (0 <= model.rgb <= 0xFFFFFFFF):
        raise ValueError("rgb must be a uint32")
    return model


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
    on: bool | None = None
    brightness: int | None = None
    color_temp: int | None = None
    rgb: int | None = None

    @model_validator(mode="after")
    def on_or_params(self) -> SetLightParams:
        return _require_light_on_or_params(self)


class SetLightsParams(OpParams):
    query: str
    on: bool | None = None
    skip_unchanged: bool = True
    brightness: int | None = None
    color_temp: int | None = None
    rgb: int | None = None

    @model_validator(mode="after")
    def on_or_params(self) -> SetLightsParams:
        return _require_light_on_or_params(self)


class SetCommandsParams(OpParams):
    items: list[dict[str, Any]]
    comment: str = ""
    skip_unchanged: bool = True


class SetClimateParams(OpParams):
    query: str | None = None
    setpoint_c: float
    force_relay: bool | None = None
    ga: str | None = None

    @model_validator(mode="after")
    def query_or_ga(self) -> SetClimateParams:
        if not self.query and not self.ga:
            raise ValueError("either query or ga is required")
        return self


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


class SetOnParams(OpParams):
    """Binary switch writes (AI-SRV plug, projector)."""

    on: bool


class GetCommandStatusParams(OpParams):
    request_id: str
