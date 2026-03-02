from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HouseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    house_id: str
    created_at: datetime
    last_seen: datetime | None
    online_status: str
    is_active: bool
    object_count: int
    device_count: int = 0
    current_schema_hash: str | None


class HouseDetail(HouseRead):
    model_config = ConfigDict(from_attributes=True)

    active_object_count: int
    schema_versions_count: int


class HouseUpdate(BaseModel):
    is_active: bool | None = None
