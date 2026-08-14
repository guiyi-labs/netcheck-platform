"""Nmap 增强发现：若系统装有 nmap，则用其替代纯 socket 探测提升速度与信息量。

- nmap_ping_sweep：`nmap -sn`（仅主机发现），解析 "Nmap scan report for <ip>"
- nmap_port_scan：`nmap -sT -p <ports> --open` 解析开放端口
- 任一函数在 nmap 缺失/异常时返回 None，调用方回退到原有 socket 探测。
"""
import shutil
import subprocess

from app.core.config import settings

NMAP_SCAN_RE = None  # 占位，实际用字符串匹配以保持零依赖


def _nmap_available() -> bool:
    return shutil.which("nmap") is not None


def nmap_ping_sweep(targets: list[str]) -> set[str] | None:
    """批量主机发现，返回活跃 IP 集合。

    - nmap 缺失或执行异常时返回 None（调用方回退到原探测方式）；
    - 正常执行时返回集合（可能为空集，表示无存活主机）。
    """
    if not _nmap_available() or not targets:
        return None
    try:
        completed = subprocess.run(
            ["nmap", "-sn", "-T4", "--max-retries", "1", "--max-rtt-timeout", "1500ms"] + targets,
            capture_output=True,
            text=True,
            timeout=max(30, len(targets) * 2),
            check=False,
        )
    except Exception:
        return None
    alive: set[str] = set()
    for line in (completed.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("Nmap scan report for"):
            alive.add(line.rsplit("for ", 1)[-1].strip())
    return alive


def nmap_port_scan(ip: str, ports: list[int]) -> list[int] | None:
    """扫描开放端口。nmap 缺失/异常返回 None（回退 socket）；正常返回列表（可能为空）。"""
    if not _nmap_available() or not ports:
        return None
    port_arg = ",".join(str(port) for port in ports)
    try:
        completed = subprocess.run(
            ["nmap", "-sT", "-Pn", "-p", port_arg, "--open", "--max-retries", "1", ip],
            capture_output=True,
            text=True,
            timeout=max(15, len(ports) * 2),
            check=False,
        )
    except Exception:
        return None
    opened: list[int] = []
    for line in (completed.stdout or "").splitlines():
        line = line.strip()
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "open":
            port_token = parts[0].split("/", 1)[0]
            if port_token.isdigit():
                opened.append(int(port_token))
    return opened