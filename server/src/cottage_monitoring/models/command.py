import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cottage_monitoring.models.base import Base


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (
        Index("idx_commands_house_ts", "house_id", "ts_sent"),
        Index("idx_commands_status", "status", postgresql_where="status = 'sent'"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    house_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("houses.house_id"), nullable=False
    )
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ts_sent: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ts_ack: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="sent")
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
