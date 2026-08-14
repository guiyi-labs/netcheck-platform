from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Asset(Base):
    """网络资产台账。后续巡检、诊断、报告均围绕此表展开。"""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    ip: Mapped[str] = mapped_column(String(64), index=True)
    hostname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    os_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ports: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AssetChangeLog(Base):
    """资产变更日志：字段级记录资产的新增/更新/删除，用于变更追溯。"""

    __tablename__ = "asset_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))  # create / update / delete
    field: Mapped[str] = mapped_column(String(64), default="")
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
