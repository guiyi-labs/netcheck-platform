"""N2 配置备份与差异。

- 配置读取命令固定来自 CONFIG_READ_COMMANDS allowlist（不做配置下发/任意命令）
- 配置文件全文不落库：仅存 SHA-256 全文哈希 + 脱敏后的文本
- 同内容去重：hash 相同不产生新快照
- 差异为相邻快照行级 diff（新增/删除/修改行）
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.device import (
    CONFIG_READ_COMMANDS,
    DeviceConfigSnapshot,
    MAX_CONFIG_SNAPSHOT_BYTES,
    SSH_VENDOR_ADAPTERS,
)
from app.services.ssh_collector import HostKeyPolicy, _transport_factory

logger = logging.getLogger("netcheck.device")

_SECRET_LINE_RE = re.compile(
    r"\b(?:password|secret|community|auth-key|priv-key|psk|access-key|key)\b",
    re.IGNORECASE,
)
# 有序匹配明确密钥行；组 1 保存"标签+可选类型号"，剩余为需遮蔽的值
_KEY_SECRET_PATTERNS = [
    (re.compile(r"(snmp-server\s+community\s+)\S+", re.IGNORECASE)),
    (re.compile(r"(enable\s+secret(?:\s+\d)?\s+)\S+", re.IGNORECASE)),
    (re.compile(r"(enable\s+password(?:\s+\d)?\s+)\S+", re.IGNORECASE)),
    (re.compile(r"(username\s+\S+\s+password(?:\s+\d)?\s+)\S+", re.IGNORECASE)),
    (re.compile(r"(key\s\S+\s+secret(?:\s+\d)?\s+)\S+", re.IGNORECASE)),
    (re.compile(r"(\S+key\s+)\S+$", re.IGNORECASE)),  # access-key/wpa-psk/auth-key 尾值
]
_TRUE_SECRET_TAGS = ("enable secret", "enable password", "snmp-server community",
                     "username .* password", "keyring", "password 7", "password 0",
                     "secret 5", "secret 9", "auth-key", "priv-key", "wpa-psk",
                     "password 密")


def redact_secret_value(line: str) -> str:
    """脱敏一行配置中的密钥值。

    原则：只遮蔽值部分，保留标签与类型号（如 enable secret 5），非密钥行原样返回。
    """
    if not line.strip():
        return line
    for pat in _KEY_SECRET_PATTERNS:
        m = pat.match(line)
        if m:
            label = m.group(1).rstrip()
            return label + " ********"
    # 含 password/secret/community/key 关键字的通用行：遮蔽最后一个词
    low = line.lower().strip()
    if any(tag in low for tag in _TRUE_SECRET_TAGS) or _SECRET_LINE_RE.search(line):
        parts = line.rstrip().rsplit(None, 1)
        if len(parts) == 2:
            return parts[0] + " ********"
    return line


def redact_config(text: str) -> str:
    """逐行脱敏整份配置，并折叠命令行界面控制字符。"""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        out.append(redact_secret_value(line))
    return "\n".join(out)


def config_full_sha256(text: str) -> str:
    """全文 SHA-256（去重 + 变更检测用，不保存明文）。"""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


@dataclass
class ConfigCollectResult:
    status: str  # ok / host_key_unknown / host_key_mismatch / auth_failed /
    # conn_refused / timeout / cmd_not_supported / error
    error: str | None = None
    full_text: str = ""          # 原始全文（内存中，不落库）
    redacted: str = ""           # 脱敏文本（落库）
    full_hash: str = ""          # 全文 SHA-256
    command: str = ""            # 使用的配置读取命令
    host_key_fingerprint: str | None = None


async def _collect_config_ssh(host: str, port: int, username: str,
                              password: str | None, key_pem: str | None,
                              vendor: str, host_key_fingerprint: str | None,
                              max_bytes: int) -> ConfigCollectResult:
    """通过 SSH 只读执行厂商配置读取命令（allowlist 内），返回脱敏结果。"""
    vendor = (vendor or "generic").lower()
    if vendor not in SSH_VENDOR_ADAPTERS:
        return ConfigCollectResult(status="error", error=f"不支持的厂商适配器: {vendor}")
    commands = CONFIG_READ_COMMANDS.get(vendor, [])
    if not commands:
        return ConfigCollectResult(status="cmd_not_supported",
                                   error=f"{vendor} 无配置读取命令")

    # 解析私钥（优先 Ed25519，其次 RSA）
    pkey = None
    if key_pem:
        try:
            pkey = __import__("paramiko").Ed25519Key.from_private_key_string(key_pem)
        except Exception:
            try:
                pkey = __import__("paramiko").RSAKey.from_private_key_string(key_pem)
            except Exception:
                pass

    policy = HostKeyPolicy(host_key_fingerprint)
    try:
        client = await _transport_factory.connect(
            host, port, username, password, pkey, policy
        )
    except __import__("paramiko").AuthenticationException:
        return ConfigCollectResult(status="auth_failed", error="SSH 认证失败")
    except __import__("paramiko").SSHException as exc:
        msg = str(exc).lower()
        if "host key" in msg:
            if policy.captured and not policy.expected:
                return ConfigCollectResult(
                    status="host_key_unknown",
                    error=f"首次连接 host key 未知，fingerprint={policy.captured}",
                    host_key_fingerprint=policy.captured,
                )
            return ConfigCollectResult(status="host_key_mismatch", error=str(exc))
        return ConfigCollectResult(status="error", error=str(exc))
    except TimeoutError:
        return ConfigCollectResult(status="timeout", error="SSH 连接超时")
    except ConnectionRefusedError:
        return ConfigCollectResult(status="conn_refused", error="SSH 连接被拒绝")
    except Exception as exc:
        logger.warning("SSH 连接异常 %s: %s", host, exc)
        return ConfigCollectResult(status="error", error=str(exc))

    # 顺序重试多条候选命令，取第一条有输出的
    try:
        for cmd in commands:
            try:
                _, stdout, _ = client.exec_command(cmd, timeout=settings.ssh_timeout)
                output = stdout.read().decode("utf-8", errors="replace")
            except Exception as exc:
                msg = str(exc).lower()
                if any(k in msg for k in ("not found", "unknown command", "no such",
                                           "invalid input", "no command")):
                    logger.debug("命令 %s 不支持: %s", cmd, exc)
                    continue
                return ConfigCollectResult(status="error", error=f"命令执行失败 {cmd}: {exc}")
            if output and output.strip():
                # 有界：截断
                if len(output.encode("utf-8", errors="replace")) > max_bytes:
                    output = output[:max_bytes]
                full = output
                redacted = redact_config(full)
                return ConfigCollectResult(
                    status="ok",
                    full_text=full,
                    redacted=redacted,
                    full_hash=config_full_sha256(full),
                    command=cmd,
                    host_key_fingerprint=policy.captured,
                )
            logger.debug("命令 %s 无输出，尝试下一条", cmd)
        return ConfigCollectResult(status="cmd_not_supported",
                                   error="所有配置读取命令均无输出")
    finally:
        try:
            client.close()
        except Exception:
            pass


async def collect_config_snapshot(db: Session, device, max_bytes: int | None = None):
    """采集一台设备的配置并入库（去重）。返回快照 id 或空。

    凭据字段语义（与 device_collector 一致）：
    - auth_key_encrypted → SSH 登录密码
    - ssh_key_encrypted → SSH 私钥 PEM
    """
    max_bytes = max_bytes or settings.ssh_max_output_bytes or MAX_CONFIG_SNAPSHOT_BYTES
    from app.services.credential_manager import decrypt_secret
    from app.models.device import DeviceCredential

    if not device.ssh_config_id:
        return {"status": "skipped", "error": "未绑定 SSH 凭据"}
    cred = db.get(DeviceCredential, device.ssh_config_id)
    if not cred:
        return {"status": "skipped", "error": "SSH 凭据不存在"}
    try:
        password = decrypt_secret(cred.auth_key_encrypted) if cred.auth_key_encrypted else None
        key_pem = decrypt_secret(cred.ssh_key_encrypted) if cred.ssh_key_encrypted else None
    except Exception as exc:
        return {"status": "error", "error": f"凭据解密失败: {exc}"}

    result = await _collect_config_ssh(
        host=device.management_ip,
        port=22,
        username=cred.username or "",
        password=None,
        key_pem=key_pem or "",
        vendor=device.vendor_platform,
        host_key_fingerprint=device.host_key_fingerprint,
        max_bytes=max_bytes,
    )
    if result.status != "ok":
        return {"status": result.status, "error": result.error}

    # 去重：同 hash 已存在则不重复入库
    existing = (
        db.query(DeviceConfigSnapshot)
        .filter(
            DeviceConfigSnapshot.device_id == device.id,
            DeviceConfigSnapshot.config_full_hash == result.full_hash,
        )
        .first()
    )
    if existing:
        return {
            "status": "unchanged",
            "snapshot_id": existing.id,
            "hash": result.full_hash,
            "device_id": device.id,
        }

    prev = (
        db.query(DeviceConfigSnapshot)
        .filter(DeviceConfigSnapshot.device_id == device.id)
        .order_by(DeviceConfigSnapshot.collected_at.desc())
        .first()
    )
    changed = prev is not None and prev.config_full_hash != result.full_hash

    snap = DeviceConfigSnapshot(
        device_id=device.id,
        vendor_platform=device.vendor_platform,
        config_full_hash=result.full_hash,
        config_text_redacted=result.redacted,
        source="ssh",
        changed=changed,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    # 登记 host key 指纹（首次采集）
    if result.host_key_fingerprint and device.host_key_fingerprint != result.host_key_fingerprint:
        device.host_key_fingerprint = result.host_key_fingerprint
        db.commit()
    return {
        "status": "ok",
        "snapshot_id": snap.id,
        "changed": changed,
        "hash": result.full_hash,
        "command": result.command,
        "device_id": device.id,
    }


@dataclass
class ConfigDiffLine:
    kind: str  # add / del / context
    old_line_no: int | None = None
    new_line_no: int | None = None
    text: str = ""


def diff_configs(old_text: str, new_text: str) -> list[dict]:
    """行级统一 diff（LCS），返回结构化变更行。"""
    import difflib

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    result: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                result.append({
                    "kind": "context",
                    "old_line_no": k + 1,
                    "new_line_no": j1 + (k - i1) + 1,
                    "text": old_lines[k],
                })
        elif tag == "delete":
            for k in range(i1, i2):
                result.append({
                    "kind": "del",
                    "old_line_no": k + 1,
                    "new_line_no": None,
                    "text": old_lines[k],
                })
        elif tag == "insert":
            for k in range(j1, j2):
                result.append({
                    "kind": "add",
                    "old_line_no": None,
                    "new_line_no": k + 1,
                    "text": new_lines[k],
                })
        elif tag == "replace":
            for k in range(i1, i2):
                result.append({
                    "kind": "del",
                    "old_line_no": k + 1,
                    "new_line_no": None,
                    "text": old_lines[k],
                })
            for k in range(j1, j2):
                result.append({
                    "kind": "add",
                    "old_line_no": None,
                    "new_line_no": k + 1,
                    "text": new_lines[k],
                })
    return result


def format_diff_text(diff_lines: list[dict]) -> str:
    """将结构化 diff 转成统一格式文本（日志/审计用）。"""
    prefix = {"add": "+", "del": "-", "context": " "}
    return "\n".join(f"{prefix.get(d['kind'], ' ')}{d['text']}" for d in diff_lines)