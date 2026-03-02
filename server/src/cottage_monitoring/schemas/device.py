from datetime import datetime

from pydantic import BaseModel


class DeviceRead(BaseModel):
    house_id: str
    device_id: str
    created_at: datetime
    last_seen: datetime | None = None
    online_status: str = "unknown"
    is_active: bool = True

    model_config = {"from_attributes": True}


class DeviceDetail(DeviceRead):
    pass


class DeviceUpdate(BaseModel):
    is_active: bool | None = None
