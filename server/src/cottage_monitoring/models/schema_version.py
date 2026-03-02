from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cottage_monitoring.models.base import Base


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    house_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("houses.house_id"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default="")
    schema_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_meta_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
