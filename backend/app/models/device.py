"""设备资产与设备凭据模型：支持 SNMPv3 / SSH 只读采集链路。

- Device: 设备资产（管理地址、厂商平台、SNMP/SSH 能力与采集状态）
- DeviceCredential: 加密存储的协议凭据（SNMPv3 authPriv / SSH），API 永不返回密钥
- SnmpInterfaceMetric: 接口 64 位计数器快照与速率
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Float, Index, func, UniqueConstraint
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# ---- SNMPv3 authPriv 允许的算法（显式 allowlist） ----
SNMP_AUTH_PROTOCOLS = {
    "SHA": "USM_AUTH_HMAC96_SHA",
    "SHA-256": "USM_AUTH_HMAC192_SHA256",
    "MD5": "USM_AUTH_HMAC96_MD5",  # 允许但标记为弱
}
SNMP_PRIV_PROTOCOLS = {
    "AES-128": "USM_PRIV_CFB128_AES",
    "AES-256": "USM_PRIV_CFB256_AES",
    "DES": "USM_PRIV_CBC56_DES",  # 允许但标记为弱
    "3DES": "USM_PRIV_CBC168_3DES",
}

# SSH 固定厂商适配器 allowlist
SSH_VENDOR_ADAPTERS = {"linux", "cisco_ios", "h3c_comware", "generic"}

# SSH 只读命令 allowlist（不允许任意命令拼接）
SSH_READONLY_COMMANDS = {
    "linux": ["hostname -f", "uname -a", "ip -o link show", "ip route show",
              "cat /etc/hosts", "uptime", "free -h", "df -h"],
    "cisco_ios": ["show version", "show ip interface brief", "show ip route",
                  "show interfaces status", "show clock"],
    "h3c_comware": ["display version", "display interface brief",
                    "display ip routing-table", "display clock"],
    "generic": ["hostname", "uname -a"],
}

# N2 配置备份：厂商 → 只读配置读取命令（仍属 allowlist，禁止任意命令拼接）
CONFIG_READ_COMMANDS = {
    "linux": ["cat /etc/network/interfaces", "cat /etc/ssh/sshd_config",
              "cat /etc/hosts"],
    "cisco_ios": ["show running-config"],
    "h3c_comware": ["display current-configuration"],
    "generic": ["hostname"],
}
# 单次配置备份允许的最大行数/字节数（N2 有界）
MAX_CONFIG_SNAPSHOT_BYTES = 1024 * 512  # 512 KB

# OID allowlist（SNMP GET/WALK 只允许这些 OID）
OID_ALLOWLIST: dict[str, list[str]] = {
    "sys": [
        "1.3.6.1.2.1.1.1.0",  # sysDescr
        "1.3.6.1.2.1.1.3.0",  # sysUpTime
        "1.3.6.1.2.1.1.5.0",  # sysName
        "1.3.6.1.2.1.1.4.0",  # sysContact
        "1.3.6.1.2.1.1.6.0",  # sysLocation
        "1.3.6.1.2.1.1.7.0",  # sysServices
    ],
    "if": [
        "1.3.6.1.2.1.2.1.0",    # ifNumber
        "1.3.6.1.2.1.2.2.1.1",  # ifIndex
        "1.3.6.1.2.1.2.2.1.2",  # ifDescr
        "1.3.6.1.2.1.2.2.1.3",  # ifType
        "1.3.6.1.2.1.2.2.1.5",  # ifSpeed
        "1.3.6.1.2.1.2.2.1.7",  # ifAdminStatus
        "1.3.6.1.2.1.2.2.1.8",  # ifOperStatus
        "1.3.6.1.2.1.2.2.1.10", # ifInOctets
        "1.3.6.1.2.1.2.2.1.16", # ifOutOctets
        "1.3.6.1.2.1.2.2.1.14", # ifInErrors
        "1.3.6.1.2.1.2.2.1.20", # ifOutErrors
        "1.3.6.1.2.1.2.2.1.13", # ifInDiscards
        "1.3.6.1.2.1.2.2.1.19", # ifOutDiscards
    ],
    "lldp": [
        "1.0.8802.1.1.2.1.1.1.0",   # lldpLocChassisId
        "1.0.8802.1.1.2.1.1.2.0",   # lldpLocSysName
        "1.0.8802.1.1.2.1.1.3.0",   # lldpLocSysDesc
        "1.0.8802.1.1.2.1.3",       # lldpRemTable 子树
        "1.0.8802.1.1.2.1.4",       # lldpStatsTable 子树
    ],
}

# 所有允许的 OID 拼合
ALL_ALLOWED_OIDS = set()
for oids in OID_ALLOWLIST.values():
    ALL_ALLOWED_OIDS.update(oids)
# 子树前缀（用于 WALK）
OID_SUBTREE_PREFIXES = {
    "if_table": "1.3.6.1.2.1.2.2.1",
    "if_number": "1.3.6.1.2.1.2.1.0",
    "lldp_rem": "1.0.8802.1.1.2.1.3",
    "lldp_stats": "1.0.8802.1.1.2.1.4",
}

# 采集上限
MAX_SNMP_INTERFACES = 256
MAX_SNMP_REQUESTS = 50
MAX_SSH_OUTPUT_BYTES = 1024 * 1024  # 1MB
MAX_SNMP_TIMEOUT = 10  # seconds
MAX_SSH_TIMEOUT = 15  # seconds
MAX_DEVICE_COLLECTIONS_PER_RUN = 32


class Device(Base):
    """网络设备资产（SNMPv3 / SSH）。"""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    management_ip: Mapped[str] = mapped_column(String(64), index=True)
    vendor_platform: Mapped[str] = mapped_column(
        String(64), default="generic"
    )  # linux/cisco_ios/generic
    snmp_config_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    ssh_config_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    host_key_fingerprint: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    # 上次采集
    last_collected_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    collect_status: Mapped[str] = mapped_column(
        String(32), default="idle"
    )  # idle/collecting/success/failed/unknown
    last_collect_error: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    # 设备事实（SNMP sys* / SSH hostname）
    sys_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sys_descr: Mapped[str | None] = mapped_column(Text, nullable=True)
    sys_uptime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    os_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class DeviceCredential(Base):
    """设备凭据（AES-256-GCM 加密存储）。"""

    __tablename__ = "device_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    protocol: Mapped[str] = mapped_column(
        String(16), index=True
    )  # snmp_v3 / ssh
    username: Mapped[str] = mapped_column(String(128))
    # 加密存储的密钥
    auth_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    priv_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssh_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 算法选择
    auth_algorithm: Mapped[str] = mapped_column(
        String(16), default="SHA-256"
    )  # SHA/SHA-256
    priv_algorithm: Mapped[str] = mapped_column(
        String(16), default="AES-128"
    )  # AES-128/AES-256
    # 可选：外部 secret 引用（vault/k8s secret name）
    external_secret_ref: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class SnmpInterfaceMetric(Base):
    """接口计数器快照（Counter64 入出字节 + 速率）。"""

    __tablename__ = "snmp_interface_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"), index=True
    )
    interface_index: Mapped[int] = mapped_column(Integer)
    interface_name: Mapped[str] = mapped_column(String(128))
    interface_descr: Mapped[str | None] = mapped_column(String(256), nullable=True)
    admin_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oper_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    if_speed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Counter64
    if_in_octets: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    if_out_octets: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # 速率（从相邻样本计算）
    in_rate_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    out_rate_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    # N4 错误/丢包计数器（最新值）
    in_errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    out_errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_discards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    out_discards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 上一个样本的时间与值（用于相邻计算）
    prev_in_octets: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    prev_out_octets: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    prev_collected_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    # 状态标记
    status: Mapped[str] = mapped_column(
        String(16), default="unknown"
    )  # unknown/ok/down
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class DeviceConfigSnapshot(Base):
    """N2 配置快照：备份设备只读配置（脱敏后存储 + 内容哈希去重）。

    - config_full_hash: 内容 SHA-256（用于去重与变更检测，不保存明文）
    - config_text_redacted: 脱敏后的配置文本（password/secret/community/key/PEM 已遮蔽）
    - truncated: 采集时输出超限未读取完整内容（hash 仅代表已读部分）
    - 同内容配置不重复入库，仅当 hash 变化才产生新快照
    - (device_id, config_full_hash) 唯一约束保证并发去重安全
    """

    __tablename__ = "device_config_snapshots"
    __table_args__ = (
        # 并发去重：DB 级唯一约束，冲突时快速失败（N2.1 P1）
        UniqueConstraint(
            "device_id", "config_full_hash",
            name="uq_device_config_hash",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    vendor_platform: Mapped[str] = mapped_column(String(64), default="generic")
    config_full_hash: Mapped[str] = mapped_column(String(64), index=True)
    config_text_redacted: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="ssh")  # ssh / manual
    changed: Mapped[bool] = mapped_column(default=False)  # 与上一快照相比是否变化
    truncated: Mapped[bool] = mapped_column(default=False)  # 输出超限标记（N2.1）
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class InterfaceMetricSample(Base):
    """N4 接口指标时间序列样本（append-only 历史表，配合最新状态表使用）。

    - (device_id, interface_index, collected_at) 标识一次观测，采集侧主键，
      接口重命名时 index 保持不变（名称随时间可变化）。
    - sys_uptime: 采集时刻设备 sysUpTime（ticks）。比上一设备级样本变小 → restart。
    - sample_marker: ok / restart / wrap / gap，用于渲染断线与重启语义。
    - in/out_bps 为采集时按相邻样本与真实时间间隔计算的结果；原始计数器一并保留。
    """

    __tablename__ = "interface_metric_samples"
    __table_args__ = (
        Index("ix_ims_device_time", "device_id", "collected_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    interface_index: Mapped[int] = mapped_column(Integer)
    interface_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    in_octets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    out_octets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    out_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    out_errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_discards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    out_discards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oper_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sys_uptime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_marker: Mapped[str] = mapped_column(String(16), default="ok")  # ok/restart/wrap/gap
    source: Mapped[str] = mapped_column(String(16), default="snmp")  # snmp / ssh / manual


class ConfigChangeEvent(Base):
    """N4 配置变化事件（独立于巡检 run 的事实表）。

    - 一次真实配置变化（DeviceConfigSnapshot.changed=True）产生一个事件；
    - (device_id, snapshot_id) 唯一：同一快照只记一次（并发采集中 DB 约束兜底）；
    - alert_key: device:{id}:config_change:{diff_hash} — 同一 diff 不重复触发，
      直到配置再次变化产生新 diff_hash；
    - 设备→资产映射缺失时置 resolved=False 并记录原因，不生成孤儿 Alert。
    """

    __tablename__ = "config_change_events"
    __table_args__ = (
        UniqueConstraint("device_id", "snapshot_id", name="uq_config_event_snapshot"),
        Index("ix_config_event_key", "alert_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("device_config_snapshots.id"), index=True
    )
    diff_hash: Mapped[str] = mapped_column(String(64), index=True)
    alert_key: Mapped[str] = mapped_column(String(255))
    changed_lines: Mapped[int] = mapped_column(Integer, default=0)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 关联 Alert.id
    resolved: Mapped[bool] = mapped_column(default=False)  # 通知已投递（无需再触发）
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
