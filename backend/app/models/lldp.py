"""N4 LLDP 邻居观测模型。

- lldp_observation: 记录每次 SNMP WALK 发现的 LLDP 邻居事实（观测层），
  设备→接口→远端邻居；远端若能解析为已知设备则建立拓扑边（推导层），
  但拓扑推导不在本表实现，留待拓扑 API 消费。
- lldpRemTimeMark 是 SNMP 行索引语义的一部分（非 Unix 时间戳），
  不应误用为 last_seen；first_seen/last_seen 由采集时间戳维护。
"""
from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LldpObservation(Base):
    """LLDP 邻居观测事实（设备→接口→远端邻居，最近活动 upsert）。

    逻辑身份：(device_id, local_port_index, remote_chassis_id, remote_port_id)
    连续采集同一邻居时仅更新 last_seen/sysname 等（不无限增长）；
    远端消失后 last_seen 停止更新，历史观测保留（由消费方判断过期）。
    索引语义：lldp_time_mark/lldp_index 为 lldpRemTable 行索引（非时间戳），
    仅用于区分同端口多邻居与追踪行变化。
    """

    __tablename__ = "lldp_observations"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "local_port_index", "remote_chassis_id", "remote_port_id",
            name="uq_lldp_neighbor_identity",
        ),
        Index("ix_lldp_device_last_seen", "device_id", "last_seen"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    local_port_index: Mapped[int] = mapped_column(Integer)
    local_port_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lldp_time_mark: Mapped[int] = mapped_column(Integer, default=0)
    lldp_index: Mapped[int] = mapped_column(Integer, default=1)
    remote_chassis_subtype: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remote_chassis_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_port_subtype: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remote_port_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_sysname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote_sysdesc: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
