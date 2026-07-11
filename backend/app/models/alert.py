from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("inspection_runs.id"), index=True)
    result_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_results.id"), nullable=True, index=True)
    diagnosis_id: Mapped[int | None] = mapped_column(ForeignKey("diagnosis_records.id"), nullable=True, index=True)
    alert_title: Mapped[str] = mapped_column(String(128))
    alert_level: Mapped[str] = mapped_column(String(16), index=True)
    alert_status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    alert_key: Mapped[str] = mapped_column(String(255), index=True)
    check_type: Mapped[str] = mapped_column(String(16), index=True)
    fault_type: Mapped[str] = mapped_column(String(64), index=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_triggered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    trigger_count: Mapped[int] = mapped_column(Integer, default=1)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recovery_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    asset = relationship("Asset")
    run = relationship("InspectionRun")
    result = relationship("InspectionResult")
    diagnosis = relationship("DiagnosisRecord")


class AlertPolicy(Base):
    __tablename__ = "alert_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    slow_response_threshold: Mapped[int] = mapped_column(Integer, default=2000)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=3)
    recovery_threshold: Mapped[int] = mapped_column(Integer, default=2)
    deduplicate_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
