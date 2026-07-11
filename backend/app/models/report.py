from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_name: Mapped[str] = mapped_column(String(128), index=True)
    report_type: Mapped[str] = mapped_column(String(32), index=True)
    report_date: Mapped[str] = mapped_column(String(16), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_runs.id"), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_tasks.id"), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
