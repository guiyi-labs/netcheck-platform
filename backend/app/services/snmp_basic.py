"""SNMP 基础采集：基于 net-snmp 命令行（snmpget/snmpwalk）做只读 GET/WALK。

- 未安装 net-snmp 或目标不支持时返回 None，由调用方优雅降级；
- 仅支持 SNMPv2c 只读（community 认证），不实现写操作；
- 常用 OID 预置于 INTERESTING_OIDS，方便资产信息补全。
"""
import shutil
import subprocess

OID_SYSDESCR = "1.3.6.1.2.1.1.1.0"       # 系统描述
OID_SYSNAME = "1.3.6.1.2.1.1.5.0"        # 系统名称
OID_SYSUPTIME = "1.3.6.1.2.1.1.3.0"      # 系统运行时长（百分秒）
OID_SYSCONTACT = "1.3.6.1.2.1.1.4.0"     # 系统联系人
OID_SYSLOCATION = "1.3.6.1.2.1.1.6.0"    # 系统位置
OID_IFNUMBER = "1.3.6.1.2.1.2.1.0"       # 接口数量
OID_IFDESCR = "1.3.6.1.2.1.2.2.1.2"      # 接口名（WALK）

INTERESTING_OIDS: list[tuple[str, str]] = [
    (OID_SYSDESCR, "系统描述"),
    (OID_SYSNAME, "系统名称"),
    (OID_SYSUPTIME, "运行时长"),
    (OID_SYSCONTACT, "联系人"),
    (OID_SYSLOCATION, "位置"),
    (OID_IFNUMBER, "接口数量"),
]

TIMEOUT_SECONDS = 8


def _snmp_tools_available() -> bool:
    return shutil.which("snmpget") is not None and shutil.which("snmpwalk") is not None


def _run(*args: str) -> list[str] | None:
    try:
        completed = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        lines = (completed.stdout or "").splitlines()
        # snmp 命令行退出码 0 为成功；超时/超时返回 1 时仍可能有部分输出
        return lines if completed.returncode == 0 or lines else None
    except Exception:
        return None


def _parse_value(line: str) -> str | None:
    """'xxx = STRING: value' 或 'xxx = INTEGER: 5' -> value；无法解析返回 None。"""
    if "=" not in line:
        return None
    raw = line.split("=", 1)[1].strip()
    if ":" in raw:
        raw = raw.split(":", 1)[1].strip()
    return raw


def snmp_get(target: str, oid: str, community: str = "public") -> str | None:
    """SNMP GET 单个 OID，返回字符串值；失败返回 None。"""
    if not _snmp_tools_available():
        return None
    lines = _run("snmpget", "-v2c", "-c", community, "-t", "3", "-r", "1", "-On", target, oid)
    if not lines:
        return None
    return _parse_value(lines[0])


def snmp_walk(target: str, oid: str, community: str = "public") -> list[tuple[str, str]] | None:
    """SNMP WALK 返回 (完整OID, 值) 列表；失败返回 None。"""
    if not _snmp_tools_available():
        return None
    lines = _run("snmpwalk", "-v2c", "-c", community, "-t", "3", "-r", "1", "-On", target, oid)
    if not lines:
        return None
    result: list[tuple[str, str]] = []
    for line in lines:
        if "=" in line:
            oid_part, _ = line.split("=", 1)
            result.append((oid_part.strip(), _parse_value(line) or ""))
    return result


def collect_device_basics(target: str, community: str = "public") -> dict | None:
    """采集设备基础信息（GET 常用 OID），全部失败返回 None。"""
    if not _snmp_tools_available():
        return None
    collected: dict = {}
    for oid, label in INTERESTING_OIDS:
        value = snmp_get(target, oid, community)
        if value is not None:
            collected[label] = value
    if not collected:
        return None
    collected["_target"] = target
    return collected