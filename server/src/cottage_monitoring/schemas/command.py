from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class CommandItem(BaseModel):
    ga: str
    value: Any


class CommandCreate(BaseModel):
    device_id: str | None = None
    ga: str | None = None
    value: Any = None
    items: list[CommandItem] | None = None
    comment: str | None = None

    @model_validator(mode="after")
    def check_ga_value_or_items(self) -> "CommandCreate":
        has_single = self.ga is not None and self.value is not None
        has_items = self.items is not None and len(self.items) > 0
        if not (has_single or has_items):
            raise ValueError("Either (ga and value) or items must be provided")
        return self


class CommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    house_id: str
    device_id: str | None = None
    ts_sent: datetime
    ts_ack: datetime | None
    status: str
    payload: dict
    results: dict | None
    retry_count: int
