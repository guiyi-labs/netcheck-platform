from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


task_assets = Table(
    "inspection_task_assets",
    Base.metadata,
    Column("task_id", ForeignKey("inspection_tasks.id"), primary_key=True),
    Column("asset_id", ForeignKey("assets.id"), primary_key=True),
)


class InspectionTask(Base):
    __tablename__ = "inspection_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_types: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    schedule_interval_minutes: Mapped[int | None] = mapped_column(nullable=True)
    # 可选 Cron 表达式（如 "0 */2 * * *"）；配置后优先于分钟间隔
    schedule_cron: Mapped[str | None] = mapped_column(String(128), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_scheduled_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    assets = relationship("Asset", secondary=task_assets)
    runs = relationship("InspectionRun", back_populates="task", cascade="all, delete-orphan")


class InspectionRun(Base):
    __tablename__ = "inspection_runs"
    __table_args__ = (Index("ix_runs_task_status", "task_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("inspection_tasks.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    trigger_type: Mapped[str] = mapped_column(String(16), default="manual", index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    task = relationship("InspectionTask", back_populates="runs")
    results = relationship("InspectionResult", back_populates="run", cascade="all, delete-orphan")
    diagnosis_records = relationship("DiagnosisRecord", back_populates="run", cascade="all, delete-orphan")


class InspectionResult(Base):
    __tablename__ = "inspection_results"
    __table_args__ = (
        Index("ix_results_run_status", "run_id", "status"),
        Index("ix_results_asset_checked", "asset_id", "checked_at"),
        Index("ix_results_checked_at", "checked_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("inspection_runs.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    check_type: Mapped[str] = mapped_column(String(16), index=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    response_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    run = relationship("InspectionRun", back_populates="results")
    asset = relationship("Asset")
    diagnosis_records = relationship("DiagnosisRecord", back_populates="result", cascade="all, delete-orphan")


class DiagnosisRecord(Base):
    __tablename__ = "diagnosis_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("inspection_runs.id"), index=True)
    result_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_results.id"), nullable=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    check_type: Mapped[str] = mapped_column(String(16), index=True)
    fault_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    suggestion: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    run = relationship("InspectionRun", back_populates="diagnosis_records")
    result = relationship("InspectionResult", back_populates="diagnosis_records")
    asset = relationship("Asset")


class TaskLock(Base):
    """分布式调度锁：多实例环境下防止同一巡检任务被并发重复执行。

    - 同一 task_id 同一时刻只能被一个 worker（实例）持有；
    - expires_at 为锁超时（默认加锁后 10 分钟），过期后其他实例可抢占；
    - 实例正常结束时主动释放锁（execute_lock.release_lock）。
    """

    __tablename__ = "task_locks"

    task_id: Mapped[int] = mapped_column(ForeignKey("inspection_tasks.id"), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    acquired_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)
