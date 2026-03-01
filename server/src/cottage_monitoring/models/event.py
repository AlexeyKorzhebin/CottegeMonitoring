from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cottage_monitoring.models.base import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_events_house_ts", "house_id", "ts"),
        Index("idx_events_house_ga_ts", "house_id", "ga", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    house_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ga: Mapped[str | None] = mapped_column(String(16), nullable=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    datatype: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    server_received_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
