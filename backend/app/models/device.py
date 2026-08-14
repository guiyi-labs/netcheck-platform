"""设备资产与设备凭据模型：支持 SNMPv3 / SSH 只读采集链路。

- Device: 设备资产（管理地址、厂商平台、SNMP/SSH 能力与采集状态）
- DeviceCredential: 加密存储的协议凭据（SNMPv3 authPriv / SSH），API 永不返回密钥
- SnmpInterfaceMetric: 接口 64 位计数器快照与速率
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Float, func
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
SSH_VENDOR_ADAPTERS = {"linux", "cisco_ios", "generic"}

# SSH 只读命令 allowlist（不允许任意命令拼接）
SSH_READONLY_COMMANDS = {
    "linux": ["hostname -f", "uname -a", "ip -o link show", "ip route show",
              "cat /etc/hosts", "uptime", "free -h", "df -h"],
    "cisco_ios": ["show version", "show ip interface brief", "show ip route",
                  "show interfaces status", "show clock"],
    "generic": ["hostname", "uname -a"],
}

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
