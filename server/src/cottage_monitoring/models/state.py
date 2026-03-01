from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cottage_monitoring.models.base import Base


class CurrentState(Base):
    __tablename__ = "current_state"

    house_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("houses.house_id"), primary_key=True
    )
    ga: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    datatype: Mapped[int] = mapped_column(Integer, nullable=False)
    server_received_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
