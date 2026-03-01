from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    house_id: str
    ts: datetime
    seq: int | None
    type: str | None
    ga: str | None
    object_id: int | None
    name: str | None
    datatype: int | None
    value: Any | None
    server_received_ts: datetime


class TimeseriesPoint(BaseModel):
    ts: datetime
    value: float | None


class TimeseriesResponse(BaseModel):
    ga: str
    object_name: str | None
    interval: str
    aggregation: str
    points: list[TimeseriesPoint]
