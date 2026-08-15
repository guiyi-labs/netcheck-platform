"""设备相关 Pydantic schema：设备、凭据、采集状态、接口指标。"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Response, PageData


# ---- 设备凭据（API 只返回状态，不返回密钥） ----

class DeviceCredentialIn(BaseModel):
    name: str = Field(..., max_length=128)
    protocol: Literal["snmp_v3", "ssh"]
    username: str = Field(..., max_length=128)
    auth_key: str = Field("", description="SNMPv3 认证密钥 / SSH 密码（明文输入，加密存储）")
    priv_key: str = Field("", description="SNMPv3 隐私密钥（明文输入）")
    ssh_key: str = Field("", description="SSH 私钥 PEM 文本（明文输入，加密存储）")
    auth_algorithm: str = Field("SHA-256", description="SNMPv3 auth 算法（SHA / SHA-256）")
    priv_algorithm: str = Field("AES-128", description="SNMPv3 priv 算法（AES-128 / AES-256）")
    external_secret_ref: str = Field("", description="外部 Secret 引用（vault/k8s）")


class DeviceCredentialOut(BaseModel):
    """API 输出：只返回算法与摘要，不回显任何密钥。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    protocol: str
    username: str
    auth_algorithm: str = ""
    priv_algorithm: str = ""
    has_secret: bool = False
    external_secret_ref: str = ""
    created_at: datetime | None = None


# ---- 设备 ----

class DeviceIn(BaseModel):
    asset_id: int | None = None
    name: str = Field(..., max_length=128)
    management_ip: str = Field(..., max_length=64)
    vendor_platform: str = Field("generic", description="linux / cisco_ios / generic")
    snmp_config_id: int | None = None
    ssh_config_id: int | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    asset_id: int | None = None
    name: str
    management_ip: str
    vendor_platform: str
    snmp_config_id: int | None = None
    ssh_config_id: int | None = None
    host_key_fingerprint: str | None = None
    last_collected_at: datetime | None = None
    collect_status: str = "idle"
    last_collect_error: str | None = None
    sys_name: str | None = None
    sys_descr: str | None = None
    sys_uptime: str | None = None
    os_version: str | None = None
    hostname: str | None = None
    has_snmp: bool = False
    has_ssh: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DeviceListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    management_ip: str
    vendor_platform: str
    collect_status: str = "idle"
    sys_name: str | None = None
    last_collected_at: datetime | None = None


# ---- 采集状态 ----

class DeviceCollectStatus(BaseModel):
    id: int
    status: str
    error: str | None = None
    last_collected_at: str | None = None


class DeviceCollectRequest(BaseModel):
    """触发采集。"""
    device_ids: list[int] = Field(..., max_length=8, description="设备 ID 列表，最多 8 台")


class SnmpInterfaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    interface_index: int
    interface_name: str
    interface_descr: str | None = None
    admin_status: int | None = None
    oper_status: int | None = None
    if_speed: int | None = None
    if_in_octets: int | None = None
    if_out_octets: int | None = None
    in_rate_bps: float | None = None
    out_rate_bps: float | None = None
    status: str = "unknown"
    collected_at: datetime | None = None


# ---- 请求/响应模型 ----

class CredentialResponse(Response[DeviceCredentialOut]):
    pass


class DeviceResponse(Response[DeviceOut]):
    pass


class DeviceListResponse(Response[PageData[DeviceListOut]]):
    pass


class DeviceCollectResponse(Response[DeviceCollectStatus]):
    pass


class SnmpInterfaceResponse(Response[list[SnmpInterfaceOut]]):
    pass

# ---- N2 配置快照与差异 ----

class DeviceConfigSnapshotOut(BaseModel):
    """配置快照元信息（不含原始文本内容）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    vendor_platform: str
    config_full_hash: str
    source: str
    changed: bool
    truncated: bool = False
    is_baseline: bool = False
    collected_at: datetime


class DeviceConfigTextOut(BaseModel):
    """配置快照详情（脱敏后的文本 + 哈希 + 行数）。"""
    id: int
    device_id: int
    vendor_platform: str
    config_full_hash: str
    config_text_redacted: str
    source: str
    changed: bool
    truncated: bool = False
    is_baseline: bool = False
    collected_at: datetime


class ConfigDiffRow(BaseModel):
    kind: str  # add / del / context / skip（省略标记）
    old_line_no: int | None = None
    new_line_no: int | None = None
    text: str


class ConfigDiffOut(BaseModel):
    device_id: int
    from_snapshot_id: int
    to_snapshot_id: int
    from_collected_at: datetime
    to_collected_at: datetime
    changed: bool
    rows: list[ConfigDiffRow]
    text: str = ""           # 统一格式 diff（展示用，最多返回 diff_max_rows 行）
    capped: bool = False     # 结果已截断（超过 diff_max_rows 限制）


class ComplianceReportOut(BaseModel):
    """配置合规报告：最新快照 vs 基线（行级 diff）。

    粒度如实标注：行级 diff（非语义级）。
    """
    device_id: int
    baseline_id: int | None = None
    baseline_collected_at: datetime | None = None
    current_id: int | None = None
    current_collected_at: datetime | None = None
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    changed_lines: list[ConfigDiffRow] = []
    status: str = "warn"       # pass / warn / fail
    status_detail: str = ""


class DeviceConfigCollectIn(BaseModel):
    pass  # POST /collect 仅需 device_id（path），无 body 也可；保留以备 future


class DeviceConfigCollectOut(BaseModel):
    device_id: int
    status: str  # ok / unchanged / skipped / auth_failed / ...
    snapshot_id: int | None = None
    changed: bool | None = None
    hash: str | None = None
    command: str | None = None
    truncated: bool | None = None
    error: str | None = None


# ---- N4 网络可观测闭环 ----

class InterfaceTrendPoint(BaseModel):
    t: int  # 桶起点相对 start 的秒数
    in_bps: float | None = None
    out_bps: float | None = None
    in_errors: int | None = None
    out_errors: int | None = None
    in_discards: int | None = None
    out_discards: int | None = None
    marker: str = "ok"  # ok/restart/wrap/gap


class InterfaceTrendSeries(BaseModel):
    interface_index: int
    interface_name: str
    points: list[InterfaceTrendPoint]
    markers: dict = {}


class InterfaceTrendOut(BaseModel):
    interfaces: list[InterfaceTrendSeries]
    meta: dict


class LldpNeighborOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    local_port_index: int
    local_port_name: str | None = None
    remote_chassis_subtype: int | None = None
    remote_chassis_id: str | None = None
    remote_port_subtype: int | None = None
    remote_port_id: str | None = None
    remote_sysname: str | None = None
    remote_sysdesc: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class DeviceLldpCollectOut(BaseModel):
    device_id: int
    status: str
    neighbors: int = 0
    stored: int = 0
    error: str | None = None


class ConfigChangeEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    snapshot_id: int
    diff_hash: str
    alert_key: str
    changed_lines: int = 0
    triggered_at: datetime
    alert_id: int | None = None
    resolved: bool = False
    note: str | None = None
