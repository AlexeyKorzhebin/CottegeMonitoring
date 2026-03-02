from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    house_id: str
    ga: str
    ts: datetime
    value: Any
    datatype: int
    server_received_ts: datetime
    object_name: str | None = None
    object_tags: list[str] = []
