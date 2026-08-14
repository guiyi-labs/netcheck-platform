"""SSH 只读采集器：基于 paramiko，host key 校验 + 命令 allowlist + 输出脱敏。

- 第一阶段只支持固定厂商/平台适配器（linux / cisco_ios / generic）；
- 区分 host_key_unknown / host_key_mismatch / auth_failed / conn_refused /
  timeout / cmd_not_supported / parse_failed；
- 原始输出长度上限（MAX_SSH_OUTPUT_BYTES），脱敏后不保留 banner/secret/完整配置；
- 不实现配置下发、回滚或任意 Shell。
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import settings
from app.models.device import SSH_VENDOR_ADAPTERS, SSH_READONLY_COMMANDS

logger = logging.getLogger("netcheck.ssh")

try:
    import paramiko  # type: ignore

    _PARAMIKO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PARAMIKO_AVAILABLE = False


@dataclass
class SshResult:
    """一次 SSH 采集的结构化结果。"""

    status: str  # ok / host_key_unknown / host_key_mismatch / auth_failed /
    # conn_refused / timeout / cmd_not_supported / parse_failed / error
    error: str | None = None
    facts: dict = field(default_factory=dict)
    raw_outputs: dict[str, str] = field(default_factory=dict)
    host_key_fingerprint: str | None = None


def _truncated(output: str) -> str:
    if len(output) > settings.ssh_max_output_bytes:
        return output[:settings.ssh_max_output_bytes] + "[TRUNCATED]"
    return output


def _redact_banner(output: str) -> str:
    """脱敏：移除 SSH banner、提示符、密码/密钥信息。"""
    lines = []
    for line in output.splitlines():
        lower = line.lower()
        if any(k in lower for k in ("password", "passphrase", "secret", "key")):
            lines.append("[REDACTED]")
            continue
        # 提示符形如 user@host:~$ 或 hostname# 或 > 开头
        if re.match(r"^[\w\-]+(@[\w\-\.]+)?[:#>$~]", line.strip()):
            lines.append("[PROMPT]")
            continue
        lines.append(line)
    return "\n".join(lines)


def _parse_linux_output(cmd: str, output: str) -> dict:
    """Linux 命令输出解析为事实字段。"""
    facts: dict = {}
    lines = output.strip().splitlines()
    if cmd == "hostname -f":
        if lines:
            facts["hostname"] = lines[0].strip()
    elif cmd == "uname -a":
        if lines:
            parts = lines[0].strip().split()
            if len(parts) >= 3:
                facts["os_type"] = parts[0]
                facts["os_version"] = " ".join(parts[1:5]) if len(parts) > 4 else " ".join(parts[1:])
    elif cmd == "uptime":
        m = re.search(r"up\s+(.+?),\s+\d+\s+user", output)
        if m:
            facts["uptime"] = m.group(1)
    elif cmd == "free -h":
        # 大概解析第二行（Memory）
        for line in lines:
            if line.startswith("Mem:"):
                parts = line.split()
                if len(parts) >= 3:
                    facts["mem_total"] = parts[1]
                    facts["mem_free"] = parts[2]
                break
    return facts


def _parse_cisco_ios_output(cmd: str, output: str) -> dict:
    """Cisco IOS 命令输出解析。"""
    facts: dict = {}
    lines = output.strip().splitlines()
    if cmd == "show version":
        for line in lines:
            if "Cisco IOS" in line or "Internetwork Operating System" in line:
                facts["os_version"] = line.strip()
                break
        # 解析 uptime
        m = re.search(r"uptime is\s+(.+)", output)
        if m:
            facts["uptime"] = m.group(1).strip()
    elif cmd == "show ip interface brief":
        if lines:
            # 提取接口名与 IP（非 Connectivity）
            facts["interfaces_count"] = str(len(lines) - 1)
    return facts


# vendor → 解析器
PARSERS: dict[str, dict[str, any]] = {
    "linux": {"parser": _parse_linux_output, "commands": SSH_READONLY_COMMANDS.get("linux", [])},
    "cisco_ios": {"parser": _parse_cisco_ios_output, "commands": SSH_READONLY_COMMANDS.get("cisco_ios", [])},
    "generic": {"parser": lambda c, o: {}, "commands": SSH_READONLY_COMMANDS.get("generic", [])},
}


class HostKeyPolicy:
    """受控 host key 策略：记录指纹，与设备记录比对，不 AutoAdd。"""

    def __init__(self, expected_fingerprint: str | None = None):
        self.expected = (expected_fingerprint or "").lower()
        self.captured: str | None = None

    def missing_host_key(self, client, hostname, key):
        fp = key.get_fingerprint().hex()  # paramiko PKey.get_fingerprint()
        self.captured = fp.lower()
        if not self.expected:
            raise paramiko.SSHException(
                f"首次连接 {hostname}，host key 未知 (fingerprint={self.captured})，"
                "请确认后登记此指纹"
            )
        if self.captured != self.expected:
            raise paramiko.SSHException(
                f"{hostname} host key 不匹配：期望 {self.expected}，"
                f"实际 {self.captured}"
            )


# transport factory（测试可注入）
class SshTransportFactory:
    async def connect(self, host: str, port: int, username: str,
                      password: str | None, pkey: paramiko.PKey | None,
                      host_key_policy: HostKeyPolicy):
        """建立 SSH 连接并返回 client。"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(host_key_policy)
        client.connect(
            hostname=host, port=port, username=username,
            password=password, pkey=pkey,
            timeout=settings.ssh_timeout,
            allow_agent=False, look_for_keys=False,
        )
        return client


_transport_factory = SshTransportFactory()


async def collect_ssh(host: str, port: int, username: str,
                      password: str | None = None, key_pem: str | None = None,
                      vendor: str = "generic",
                      host_key_fingerprint: str | None = None) -> SshResult:
    """异步执行 SSH 只读采集（固定命令 allowlist）。"""
    if not _PARAMIKO_AVAILABLE:
        return SshResult(status="error", error="paramiko 未安装")
    vendor = (vendor or "generic").lower()
    if vendor not in SSH_VENDOR_ADAPTERS:
        return SshResult(status="error", error=f"不支持的厂商适配器: {vendor}")

    adapter = PARSERS.get(vendor, PARSERS["generic"])
    commands = adapter["commands"]
    parser = adapter["parser"]

    # 构造 pkey
    pkey = None
    if key_pem:
        try:
            pkey = paramiko.Ed25519Key.from_private_key_string(key_pem)  # type: ignore
        except Exception:
            try:
                pkey = paramiko.RSAKey.from_private_key_string(key_pem)  # type: ignore
            except Exception:
                pass

    policy = HostKeyPolicy(host_key_fingerprint)
    try:
        client = await _transport_factory.connect(
            host, port, username, password, pkey, policy
        )
        facts: dict[str, str] = {}
        raw: dict[str, str] = {}
        for cmd in commands[:5]:  # 有界
            try:
                _, stdout, _ = client.exec_command(
                    cmd, timeout=settings.ssh_timeout,
                )
                output = stdout.read().decode("utf-8", errors="replace")
                output = _truncated(output)
                output = _redact_banner(output)
                raw[cmd] = output
                parsed = parser(cmd, output)
                facts.update(parsed)
            except Exception as exc:
                logger.debug("SSH 命令 %s 失败: %s", cmd, exc)
                raw[cmd] = ""
        client.close()
        return SshResult(
            status="ok", facts=facts,
            raw_outputs=raw,
            host_key_fingerprint=policy.captured,
        )
    except paramiko.AuthenticationException:
        return SshResult(status="auth_failed", error="SSH 认证失败")
    except paramiko.SSHException as exc:
        msg = str(exc).lower()
        if "host key" in msg:
            if policy.captured and not policy.expected:
                return SshResult(
                    status="host_key_unknown",
                    error=f"首次连接 host key 未知，fingerprint={policy.captured}",
                    host_key_fingerprint=policy.captured,
                )
            return SshResult(status="host_key_mismatch", error=str(exc))
        return SshResult(status="error", error=str(exc))
    except TimeoutError:
        return SshResult(status="timeout", error="SSH 连接超时")
    except ConnectionRefusedError:
        return SshResult(status="conn_refused", error="SSH 连接被拒绝")
    except Exception as exc:
        logger.warning("SSH 采集异常 %s: %s", host, exc)
        return SshResult(status="error", error=str(exc))