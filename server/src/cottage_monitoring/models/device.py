from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from cottage_monitoring.models.base import Base


class Device(Base):
    __tablename__ = "devices"

    house_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("houses.house_id"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    online_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="unknown"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
