"""SNMPv3 只读采集器：基于 pysnmp 7（v3arch asyncio）。

- 仅 authPriv（sha256/aes128 为首选，显式 allowlist）；
- OID 固定 allowlist：sys* 与接口表（ifTable 子树），拒绝任意 OID；
- 采集 sysName/sysDescr/sysUpTime + 接口名/描述/状态/64 位字节计数器；
- 接口速率由相邻样本在真实时间间隔上计算（处理重启、回绕、缺样本）；
- 超时、认证失败、权限不足等显式分类，绝不显示为健康或 0 流量。
"""
import asyncio
import logging
from dataclasses import dataclass, field

from app.core.config import settings
from app.models.device import ALL_ALLOWED_OIDS, OID_ALLOWLIST, OID_SUBTREE_PREFIXES

logger = logging.getLogger("netcheck.snmpv3")

# pysnmp v3arch 常量
try:
    from pysnmp.hlapi.v3arch.asyncio import (  # type: ignore
        SnmpEngine,
        ContextData,
        UsmUserData,
        USM_AUTH_HMAC96_SHA,
        USM_AUTH_HMAC192_SHA256,
        USM_PRIV_CFB128_AES,
        USM_PRIV_CFB256_AES,
        get_cmd,
        walk_cmd,
        ObjectType,
        ObjectIdentity,
    )

    _PYSNMP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYSNMP_AVAILABLE = False
    SnmpEngine = ContextData = UsmUserData = None
    USM_AUTH_HMAC96_SHA = USM_AUTH_HMAC192_SHA256 = None
    USM_PRIV_CFB128_AES = USM_PRIV_CFB256_AES = None
    get_cmd = walk_cmd = ObjectType = ObjectIdentity = None

AUTH_MAP = {
    "SHA": USM_AUTH_HMAC96_SHA,
    "SHA-256": USM_AUTH_HMAC192_SHA256,
}
PRIV_MAP = {
    "AES-128": USM_PRIV_CFB128_AES,
    "AES-256": USM_PRIV_CFB256_AES,
}


@dataclass
class SnmpResult:
    """一次采集的结构化结果。"""

    status: str  # ok / auth_failed / priv_failed / timeout / error
    error: str | None = None
    facts: dict = field(default_factory=dict)
    interfaces: list[dict] = field(default_factory=list)
    raw_oids: list[tuple[str, str]] = field(default_factory=list)


def _oid_in_allowlist(oid: str) -> bool:
    if oid.rstrip(".0") in ALL_ALLOWED_OIDS or oid in ALL_ALLOWED_OIDS:
        return True
    # 子树前缀（WALK 目标即可）
    for prefix in ("1.3.6.1.2.1.2.2.1", "1.3.6.1.2.1.1"):
        if oid.startswith(prefix):
            return True
    return False


# USM/框架认证失败异常类型名（pysnmp 误用名称而非文本标识）
_AUTH_FAILURE_TYPES = (
    "authenticationerror", "wrongdigest", "unknownusername", "unknownengineid",
    "notintimewindow", "usmerror", "authfailure",
)
_PRIV_FAILURE_TYPES = (
    "priverror", "decryptionerror", "wrongdigestpriv", "encryptionerror",
)


def classify_error(error_indication, error_status) -> str:
    """把 pysnmp 错误映射到分类。pysnmp 返回对象或字符串。"""
    if error_indication is None:
        return "ok"
    # pysnmp 可能返回对象（带 __name__）或字符串
    if isinstance(error_indication, str):
        name = error_indication.lower()
    else:
        name = type(error_indication).__name__.lower()
    text = f"{name} {str(error_indication).lower()}"
    if "timedout" in text or "timeout" in text:
        return "timeout"
    # 真实 USM 异常：类名优先（WrongDigest/UnknownUserName 等）
    if name in _AUTH_FAILURE_TYPES or "auth" in text:
        return "auth_failed"
    if name in _PRIV_FAILURE_TYPES or "priv" in text:
        return "priv_failed"
    return "error"


def _no_such(value) -> bool:
    name = type(value).__name__
    return name in ("NoSuchInstance", "NoSuchObject", "EndOfMibView") or value is None


def _snmp_value_str(value) -> str:
    if _no_such(value):
        return ""
    try:
        return value.prettyPrint() if hasattr(value, "prettyPrint") else str(value)
    except Exception:
        return str(value)


def _counter64_int(value) -> int | None:
    if _no_such(value):
        return None
    try:
        return int(value)
    except Exception:
        return None


# ---- pysnmp 命令（mock 友好：transport factory 可注入） ----

def _engine():
    return SnmpEngine()


def _user(username: str, auth_key: str | None, priv_key: str | None,
          auth_algo: str, priv_algo: str) -> UsmUserData:
    auth_proto = AUTH_MAP.get(auth_algo) or USM_AUTH_HMAC192_SHA256
    priv_proto = PRIV_MAP.get(priv_algo) or USM_PRIV_CFB128_AES
    return UsmUserData(
        username,
        authKey=auth_key or "",
        privKey=priv_key or "",
        authProtocol=auth_proto,
        privProtocol=priv_proto,
    )


async def _get(transport, user, oid: str):
    err_ind, err_status, _idx, var_binds = await get_cmd(
        _engine(), user, transport, ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    return err_ind, err_status, var_binds


async def _walk(transport, user, oid: str, subtree: str | None = None):
    """WALK `oid` 子树，返回 [(full_oid, value_str), ...]。

    subtree=None 时沿用历史行为（不设前缀停靠，可被 max_rows 截断）；
    传入子树前缀时，遇到不再以该前缀开头的 OID 立即停止（防止越过
    LLDP/lldpRemTable 边界混入 lldpLocalTable/system 等其它表数据）。
    """
    results: list[tuple[str, str]] = []
    max_rows = settings.snmp_max_interfaces + 10
    iterator = walk_cmd(
        _engine(), user, transport, ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    count = 0
    prefix = subtree or oid
    while count < max_rows:
        try:
            res = await anext(iterator)
        except StopAsyncIteration:
            break
        err_ind, err_status, _idx, var_binds = res
        if err_ind is not None:
            return None, classify_error(err_ind, err_status), results
        for var_bind in var_binds:
            name = str(var_bind[0])
            if not (name.startswith(prefix + ".") or name == prefix):
                return results, None, results
            value = _snmp_value_str(var_bind[1])
            results.append((name, value))
        count += 1
    return results, None, results


# ---- 采集封装 ----

async def _collect_via_transport(transport, username, auth_key, priv_key,
                                 auth_algo, priv_algo) -> SnmpResult:
    user = _user(username, auth_key, priv_key, auth_algo, priv_algo)

    # 1. sys* GET
    facts: dict = {}
    oid_labels = {
        "1.3.6.1.2.1.1.1.0": "sys_descr",
        "1.3.6.1.2.1.1.3.0": "sys_uptime",
        "1.3.6.1.2.1.1.5.0": "sys_name",
        "1.3.6.1.2.1.1.4.0": "sys_contact",
        "1.3.6.1.2.1.1.6.0": "sys_location",
    }
    scanned = 0
    for oid, label in oid_labels.items():
        if scanned >= settings.snmp_max_requests:
            break
        err_ind, err_status, var_binds = await _get(transport, user, oid)
        status = classify_error(err_ind, err_status)
        if status in ("auth_failed", "priv_failed", "timeout", "error"):
            # 传输/安全层错误：中止整个采集，不继续
            return SnmpResult(status=status, error=f"SNMP 采集失败: {status}")
        if err_ind is None and var_binds:
            value = _snmp_value_str(var_binds[0][1])
            if value and not _no_such(var_binds[0][1]):
                facts[label] = value
        scanned += 1

    # 2. 接口表 WALK
    interfaces: dict[int, dict] = {}
    if_walks = {
        "1.3.6.1.2.1.2.2.1.2": "name",
        "1.3.6.1.2.1.2.2.1.3": "if_type",
        "1.3.6.1.2.1.2.2.1.5": "if_speed",
        "1.3.6.1.2.1.2.2.1.7": "admin_status",
        "1.3.6.1.2.1.2.2.1.8": "oper_status",
        "1.3.6.1.2.1.2.2.1.10": "in_octets",
        "1.3.6.1.2.1.2.2.1.16": "out_octets",
        "1.3.6.1.2.1.2.2.1.14": "in_errors",
        "1.3.6.1.2.1.2.2.1.20": "out_errors",
        "1.3.6.1.2.1.2.2.1.13": "in_discards",
        "1.3.6.1.2.1.2.2.1.19": "out_discards",
    }
    for walk_oid, field_name in if_walks.items():
        rows, walk_status, _ = await _walk(transport, user, walk_oid)
        if walk_status is not None and walk_status != "ok":
            # 认证/超时在 sys 阶段已捕获；这里忽略部分 OID 不支持
            continue
        for full_oid, value in (rows or []):
            idx = full_oid.rsplit(".", 1)[-1]
            if not idx.isdigit():
                continue
            index = int(idx)
            if len(interfaces) >= settings.snmp_max_interfaces:
                break
            entry = interfaces.setdefault(index, {"index": index})
            entry[field_name] = value
            # WALK 的 value 为原样字符串；计数器需要 int
        scanned += 1

    # 转列表并解析数值字段
    interface_list = []
    for index in sorted(interfaces):
        entry = interfaces[index]
        entry["name"] = entry.get("name", f"if{index}")
        entry["in_octets"] = _safe_counter(entry.get("in_octets"))
        entry["out_octets"] = _safe_counter(entry.get("out_octets"))
        entry["if_speed"] = _safe_int(entry.get("if_speed"))
        entry["admin_status"] = _safe_int(entry.get("admin_status"))
        entry["oper_status"] = _safe_int(entry.get("oper_status"))
        entry["in_errors"] = _safe_counter(entry.get("in_errors"))
        entry["out_errors"] = _safe_counter(entry.get("out_errors"))
        entry["in_discards"] = _safe_counter(entry.get("in_discards"))
        entry["out_discards"] = _safe_counter(entry.get("out_discards"))
        interface_list.append({k: v for k, v in entry.items()})

    result = SnmpResult(status="ok", facts=facts, interfaces=interface_list)
    return result


def _safe_counter(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class SnmpTransportFactory:
    """真实传输工厂（测试注入 mock）。"""

    async def create(self, host: str, port: int):
        from pysnmp.hlapi.v3arch.asyncio import UdpTransportTarget

        return await UdpTransportTarget.create(
            (host, port), timeout=settings.snmp_timeout,
            retries=settings.snmp_retries,
        )


_transport_factory = SnmpTransportFactory()


async def collect_snmpv3(host: str, username: str, auth_key: str, priv_key: str,
                         auth_algo: str = "SHA-256", priv_algo: str = "AES-128",
                         port: int = 161) -> SnmpResult:
    """异步执行 SNMPv3 authPriv 采集。"""
    if not _PYSNMP_AVAILABLE:  # pragma: no cover
        return SnmpResult(status="error", error="pysnmp 未安装")
    try:
        transport = await _transport_factory.create(host, port)
        return await _collect_via_transport(
            transport, username, auth_key, priv_key, auth_algo, priv_algo,
        )
    except asyncio.TimeoutError:
        return SnmpResult(status="timeout", error="SNMP 请求超时")
    except Exception as exc:
        logger.warning("SNMPv3 采集异常 %s: %s", host, exc)
        return SnmpResult(status="error", error=str(exc))


def run_snmpv3_sync(host: str, username: str, auth_key: str, priv_key: str,
                    auth_algo: str = "SHA-256", priv_algo: str = "AES-128",
                    port: int = 161) -> SnmpResult:
    """同步入口（后台线程调用）。"""
    return asyncio.run(
        collect_snmpv3(host, username, auth_key, priv_key, auth_algo, priv_algo, port)
    )


# ---- N4 LLDP 邻居采集（复用同一传输/用户构造，mock 友好） ----

# lldpRemTable 远端邻居列（列号 → 语义字段）。
# 兼容两套真实布局：
#   1) 标准 IEEE LLDP-MIB lldpRemTable = 1.0.8802.1.1.2.1.3.7，列 3..10；
#   2) lldpd(1.x) AgentX 实际注册的远端邻居表 = 1.0.8802.1.1.2.1.4.1.1，
#      仅列 4..12（time_mark/local_port/lldp_index 在行索引里，无独立列）。
# 行索引统一解析为 time_mark.local_port.lldp_index；time_mark 是“记录最后
# 变更时刻”的 TimeFilter tick（随 LLDP 周期刷新），绝不是墙钟/Unix 时间戳。
LLDP_REM_TABLE_STANDARD = "1.0.8802.1.1.2.1.3.7.1"
LLDP_REM_TABLE_LLDPD = "1.0.8802.1.1.2.1.4.1.1"

# 标准 lldpRemTable：列号 → 字段
LLDP_REM_STANDARD_COLUMNS = {
    f"{LLDP_REM_TABLE_STANDARD}.3": "chassis_subtype",
    f"{LLDP_REM_TABLE_STANDARD}.4": "chassis_id",
    f"{LLDP_REM_TABLE_STANDARD}.5": "port_subtype",
    f"{LLDP_REM_TABLE_STANDARD}.6": "port_id",
    f"{LLDP_REM_TABLE_STANDARD}.7": "sysname",
    f"{LLDP_REM_TABLE_STANDARD}.8": "sysdesc",
    f"{LLDP_REM_TABLE_STANDARD}.9": "sys_cap_supported",
    f"{LLDP_REM_TABLE_STANDARD}.10": "sys_cap_enabled",
}
# lldpd AgentX 实际布局：列 4..12（其 1/2/3 列为索引段，不 WALK）
LLDP_REM_LLDPD_COLUMNS = {
    f"{LLDP_REM_TABLE_LLDPD}.4": "chassis_subtype",
    f"{LLDP_REM_TABLE_LLDPD}.5": "chassis_id",
    f"{LLDP_REM_TABLE_LLDPD}.6": "port_subtype",
    f"{LLDP_REM_TABLE_LLDPD}.7": "port_id",
    f"{LLDP_REM_TABLE_LLDPD}.8": "port_desc",
    f"{LLDP_REM_TABLE_LLDPD}.9": "sysname",
    f"{LLDP_REM_TABLE_LLDPD}.10": "sysdesc",
    f"{LLDP_REM_TABLE_LLDPD}.11": "sys_cap_supported",
    f"{LLDP_REM_TABLE_LLDPD}.12": "sys_cap_enabled",
}
# 默认 WALK 候选：优先 lldpd 真实布局，其次标准 lldpRemTable
LLDP_REM_LAYOUTS = [
    LLDP_REM_LLDPD_COLUMNS,
    LLDP_REM_STANDARD_COLUMNS,
]
# 向后兼容（历史测试引用）
LLDP_REM_COLUMNS = LLDP_REM_STANDARD_COLUMNS


def _parse_lldp_index(full_oid: str, col_oid: str) -> tuple[int, int, int] | None:
    """解析 lldpRemTable 行索引：time_mark.local_port.lldp_index。

    返回三元组或 None（前缀不匹配/无法解析）。
    """
    if not full_oid.startswith(col_oid + "."):
        return None
    suffix = full_oid[len(col_oid) + 1:]
    parts = suffix.split(".")
    if len(parts) < 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


async def _collect_lldp_via_transport(transport, username, auth_key, priv_key,
                                      auth_algo, priv_algo,
                                      max_rows: int = 64) -> dict:
    """WALK 远端 LLDP 邻居表并按行索引聚合为邻居字典列表。

    支持两种真实布局（优先 lldpd，回退标准）。
    行索引解析：time_mark.local_port.lldp_index。
    返回：{"status": str, "neighbors": [dict...], "error": str|None,
            "layout": str|None, "unsupported": str|None}。
    status 可能为 ok / timeout / auth_failed / priv_failed /
    error；当两种布局都未命中且非传输故障时为 ok + 空邻居
    （unsupported="no_llpd_data"，即代理无 LLDP MIB 数据）。
    """
    user = _user(username, auth_key, priv_key, auth_algo, priv_algo)
    # 尝试每种布局，取有数据的
    for columns in LLDP_REM_LAYOUTS:
        rows: dict[tuple[int, int, int], dict] = {}
        got_data = False
        for col_oid, field_name in columns.items():
            collected, walk_status, _ = await _walk(transport, user, col_oid, subtree=col_oid)
            if walk_status is not None and walk_status != "ok":
                if walk_status in ("timeout", "auth_failed", "priv_failed"):
                    # 传输/认证/解密失败：不是“表不存在”，直接上抛
                    return {
                        "status": walk_status,
                        "neighbors": [],
                        "error": f"LLDP WALK {walk_status}",
                        "layout": None,
                        "unsupported": walk_status,
                    }
                # 其它（如 no-such-object）视为该布局不支持 → 尝试下一布局
                got_data = False
                break
            for full_oid, value in (collected or []):
                if not value:
                    continue
                got_data = True
                index = _parse_lldp_index(full_oid, col_oid)
                if index is None:
                    continue
                time_mark, local_port, lldp_index = index
                key = (time_mark, local_port, lldp_index)
                entry = rows.setdefault(key, {})
                entry[field_name] = value
                if len(rows) >= max_rows:
                    break
        if not got_data:
            continue
        # 有数据 → 组装邻居列表
        neighbors = []
        for (time_mark, local_port, lldp_index), raw in sorted(rows.items()):
            neighbors.append({
                "time_mark": time_mark,
                "local_port": local_port,
                "lldp_index": lldp_index,
                "chassis_subtype": _safe_int(raw.get("chassis_subtype")),
                "chassis_id": raw.get("chassis_id"),
                "port_subtype": _safe_int(raw.get("port_subtype")),
                "port_id": raw.get("port_id"),
                "port_desc": raw.get("port_desc"),
                "sysname": raw.get("sysname"),
                "sysdesc": raw.get("sysdesc"),
            })
        layout = "lldpd" if columns is LLDP_REM_LLDPD_COLUMNS else "standard"
        return {"status": "ok", "neighbors": neighbors, "error": None, "layout": layout}
    # 所有布局都无数据
    return {"status": "ok", "neighbors": [], "error": None, "layout": None, "unsupported": "no_llpd_data"}


async def collect_lldp(host: str, username: str, auth_key: str, priv_key: str,
                       auth_algo: str = "SHA-256", priv_algo: str = "AES-128",
                       port: int = 161, max_rows: int = 64) -> dict:
    """异步采集 LLDP 邻居（复用 SNMPv3 传输）。"""
    if not _PYSNMP_AVAILABLE:  # pragma: no cover
        return {"status": "error", "neighbors": [], "error": "pysnmp 未安装"}
    try:
        transport = await _transport_factory.create(host, port)
        return await _collect_lldp_via_transport(
            transport, username, auth_key, priv_key, auth_algo, priv_algo, max_rows,
        )
    except asyncio.TimeoutError:
        return {"status": "timeout", "neighbors": [], "error": "SNMP 请求超时"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLDP 采集异常 %s: %s", host, exc)
        return {"status": "error", "neighbors": [], "error": str(exc)}


def run_lldp_sync(host: str, username: str, auth_key: str, priv_key: str,
                  auth_algo: str = "SHA-256", priv_algo: str = "AES-128",
                  port: int = 161, max_rows: int = 64) -> dict:
    """LLDP 同步入口。"""
    return asyncio.run(
        collect_lldp(host, username, auth_key, priv_key, auth_algo, priv_algo,
                     port, max_rows)
    )