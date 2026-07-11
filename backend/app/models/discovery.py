from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DiscoveryScan(Base):
    __tablename__ = "discovery_scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_range: Mapped[str] = mapped_column(String(512))
    scan_mode: Mapped[str] = mapped_column(String(16), default="ping_port", index=True)
    ports: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    total_targets: Mapped[int] = mapped_column(default=0)
    discovered_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    results = relationship("DiscoveryResult", back_populates="scan", cascade="all, delete-orphan")


class DiscoveryResult(Base):
    __tablename__ = "discovery_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("discovery_scans.id"), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    hostname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    open_ports: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    already_exists: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    matched_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    imported_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    scan = relationship("DiscoveryScan", back_populates="results")
