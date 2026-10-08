import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class FileRecord(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PROCESSING")
    crs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    features: Mapped[list["FeatureRecord"]] = relationship(back_populates="file", cascade="all, delete-orphan")

class FeatureRecord(Base):
    __tablename__ = "features"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    supported: Mapped[bool] = mapped_column(nullable=False, default=True)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_hectares: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file: Mapped[FileRecord] = relationship(back_populates="features")
