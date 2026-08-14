"""Traceroute 网络诊断：调用系统 traceroute 并解析路径。

用法（服务层）：run_traceroute(target) -> dict，endpoint 层负责鉴权与超时。
本模块不产生网络副作用以外的 I/O；测试通过 monkeypatch subprocess 完成。
"""
import platform
import re
import subprocess
import time

from app.core.config import settings

MAX_HOPS_DEFAULT = 15
WAIT_DEFAULT = 1.0
TIMEOUT_SECONDS = 60

# 匹配典型 hop 行：序号 + 主机/IP + 若干 RTT（支持 * 超时）
_HOP_RE = re.compile(
    r"^\s*(?P<hop>\d+)\s+(?:"
    r"(?P<hostname>[^\s()]+)\s*\((?P<ip>[\d.]+)\)|"  # BSD: host (ip)
    r"(?P<ip_only>[\d.]+)|"  # Linux -n: raw ip
    r"\*"
    r")\s*(?P<rtts>.*)$"
)
_RTT_RE = re.compile(r"(\d+\.\d+)\s*ms|\*")


def _command(target: str, max_hops: int, wait: float) -> list[str]:
    if platform.system() == "Windows":
        return ["tracert", "-d", "-h", str(max_hops), "-w", str(int(wait * 1000)), target]
    return ["traceroute", "-n", "-m", str(max_hops), "-w", str(wait), "-q", "1", target]


def _parse_line(line: str) -> dict | None:
    match = _HOP_RE.match(line)
    if not match:
        return None
    hop = int(match.group("hop"))
    host = match.group("hostname") or ""
    ip = match.group("ip") or match.group("ip_only") or ""
    rtt_raw = match.group("rtts") or ""
    rtts: list[float | None] = []
    for m in _RTT_RE.finditer(rtt_raw):
        rtts.append(float(m.group(1)) if m.group(1) is not None else None)
    return {"hop": hop, "host": host, "ip": ip, "rtts": rtts}


def run_traceroute(target: str, max_hops: int = MAX_HOPS_DEFAULT, wait: float = WAIT_DEFAULT) -> dict:
    """执行 traceroute 并返回解析结果。

    - status: completed（到目标可达）/ failed（执行异常）/ timeout（探测完未到达目标）
    - hops: 有序跳点列表，每项含 hop/host/ip/rtts
    """
    if not target or len(target) > 255:
        return {"target": target, "status": "failed", "hops": [], "error": "目标不能为空或过长"}
    start = time.monotonic()
    try:
        completed = subprocess.run(
            _command(target, max_hops, wait),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        return {"target": target, "status": "failed", "hops": [], "error": f"traceroute 执行失败：{exc}"}

    if completed.returncode not in (0, 1, 2):
        return {
            "target": target,
            "status": "failed",
            "hops": [],
            "error": (completed.stderr or completed.stdout or "").strip() or f"退出码 {completed.returncode}",
        }

    hops = []
    reached = False
    for line in (completed.stdout or "").splitlines():
        parsed = _parse_line(line)
        if parsed:
            hops.append(parsed)
            # 只有出现目标 IP 才视为到达（中间网关不算）
            if parsed["ip"] and target == parsed["ip"]:
                reached = True

    # traceroute 退出码：0=正常到达，1=主机不可达，2=命令不当；出现目标 IP 即视为到达
    if reached:
        status = "completed"
    elif hops:
        status = "timeout"
    else:
        status = "failed"
    return {
        "target": target,
        "status": status,
        "hops": hops,
        "error": None if status == "completed" else "目标不可达或探测超时",
        "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
    }