from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cottage_monitoring.models.base import Base


class Object(Base):
    __tablename__ = "objects"
    __table_args__ = (
        Index("idx_objects_house_active", "house_id", "is_active"),
    )

    house_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("houses.house_id"), primary_key=True
    )
    ga: Mapped[str] = mapped_column(String(16), primary_key=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    datatype: Mapped[int] = mapped_column(Integer, nullable=False)
    units: Mapped[str] = mapped_column(String(32), server_default="")
    tags: Mapped[str] = mapped_column(Text, server_default="")
    comment: Mapped[str] = mapped_column(Text, server_default="")
    schema_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_timeseries: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
