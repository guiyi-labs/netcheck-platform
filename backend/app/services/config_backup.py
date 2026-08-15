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
# 有序匹配明确密钥行（可带缩进）；组 1 保存"标签+可选类型号"，剩余为需遮蔽的值
_KEY_SECRET_PATTERNS = [
    (re.compile(r"^\s*(snmp-server\s+community\s+)\S+", re.IGNORECASE)),
    (re.compile(r"^\s*(enable\s+secret(?:\s+\d)?\s+)\S+", re.IGNORECASE)),
    (re.compile(r"^\s*(enable\s+password(?:\s+\d)?\s+)\S+", re.IGNORECASE)),
    (re.compile(r"^\s*(username\s+\S+\s+password(?:\s+\d)?\s+)\S+", re.IGNORECASE)),
    (re.compile(r"^\s*(crypto\s+isakmp\s+key\s+)\S+", re.IGNORECASE)),
    (re.compile(r"^\s*(crypto\s+key\s+\S+\s+key\s+)\S+", re.IGNORECASE)),
    (re.compile(r"^\s*(key\s\S+\s+secret(?:\s+\d)?\s+)\S+", re.IGNORECASE)),
    # WireGuard：PrivateKey / PresharedKey = <base64>
    (re.compile(r"^\s*(private\s*key\s*=\s*)\S+", re.IGNORECASE)),
    (re.compile(r"^\s*(preshared\s*key\s*=\s*)\S+", re.IGNORECASE)),
    (re.compile(r"^\s*(\S+key\s+)\S+$", re.IGNORECASE)),  # access-key/wpa-psk/auth-key 尾值
]
# PEM 私钥块（多行 Secret 状态机）：BEGIN/END 头尾遮蔽，块体逐行替换
_PEM_BEGIN_RE = re.compile(r"^-----BEGIN ([A-Z0-9 ]*)PRIVATE KEY-----$", re.IGNORECASE)
_PEM_END_RE = re.compile(r"^-----END ([A-Z0-9 ]*)PRIVATE KEY-----$", re.IGNORECASE)


def redact_secret_value(line: str) -> str:
    """脱敏一行配置中的密钥值。

    原则：只遮蔽值部分，保留标签与类型号（如 enable secret 5），非密钥行原样返回。
    保留行首缩进，避免破坏配置块结构。
    """
    stripped = line.strip()
    if not stripped:
        return line
    indent = line[: len(line) - len(line.lstrip())]
    for pat in _KEY_SECRET_PATTERNS:
        m = pat.match(line)
        if m:
            label = m.group(1).rstrip()
            return indent + label + " ********"
    # 含 password/secret/community/key 关键字的通用行：遮蔽最后一个词
    if _SECRET_LINE_RE.search(stripped):
        parts = stripped.rsplit(None, 1)
        if len(parts) == 2:
            return indent + parts[0] + " ********"
    return line


def redact_config(text: str) -> str:
    """逐行脱敏整份配置（含 PEM 私钥块状态机），折叠空行。

    - 行级规则：_KEY_SECRET_PATTERNS + 通用关键字兜底
    - 多行 Secret：PEM 私钥块（BEGIN/END 之间所有行遮蔽），保持行数稳定以便 diff
    """
    out: list[str] = []
    in_pem = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if in_pem:
            if _PEM_END_RE.match(line.strip()):
                in_pem = False
                out.append("-----END PRIVATE KEY-----")
            else:
                out.append("********")  # 块体行整体遮蔽（保留行数）
            continue
        if _PEM_BEGIN_RE.match(line.strip()):
            in_pem = True
            out.append("-----BEGIN PRIVATE KEY-----")
            continue
        out.append(redact_secret_value(line))
    return "\n".join(out)


def config_full_sha256(text: str) -> str:
    """内容 SHA-256（去重 + 变更检测用，不保存明文）。

    注意：若采集超限被截断（ConfigCollectResult.truncated=True），该哈希只代表
    已读取部分的内容，不代表完整配置；响应/模型通过 truncated 显式标记。
    """
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


@dataclass
class ConfigCollectResult:
    status: str  # ok / host_key_unknown / host_key_mismatch / auth_failed /
    # conn_refused / timeout / cmd_not_supported / error
    error: str | None = None
    full_text: str = ""          # 原始内容（内存中，不落库；超过上限则为截断后内容）
    redacted: str = ""           # 脱敏文本（落库）
    full_hash: str = ""          # 内容 SHA-256（截断时为已读部分哈希，见 truncated）
    truncated: bool = False      # 是否因超限未读取完整内容
    command: str = ""            # 使用的配置读取命令
    host_key_fingerprint: str | None = None


async def _read_limited(stdout, max_bytes: int) -> tuple[str, bool]:
    """流式读取 stdout，最多 max_bytes 字节，禁止先读全量再截断。

    返回 (内容, 是否超过上限)。按字节计数并保持 UTF-8 边界：
    若读取到的字节序列在 max_bytes 边界被截断，回退到上一个完整字符边界。
    """
    chunks: list[bytes] = []
    total = 0
    truncated = False
    while True:
        chunk = stdout.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            # 丢弃超出部分；保留已读内容（可能被截断在字符中间）
            chunks.append(chunk[: max_bytes - (total - len(chunk))])
            truncated = True
            break
        chunks.append(chunk)
    data = b"".join(chunks)
    # UTF-8 边界回退：从末尾去掉不完整的字节（最多 3 字节）
    text = None
    for cut in range(0, 4):
        candidate = data[: len(data) - cut] if cut else data
        try:
            text = candidate.decode("utf-8")
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = data.decode("utf-8", errors="replace")
    return text, truncated


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
                _, stdout, stderr = client.exec_command(cmd, timeout=settings.ssh_timeout)
                # stdout 有界流式读取（不整读再截断）
                output, truncated = await _read_limited(stdout, max_bytes)
                # stderr 也有界读取：用于诊断，同时排空通道避免阻塞
                stderr_text, _ = await _read_limited(stderr, max_bytes)
            except Exception as exc:
                msg = str(exc).lower()
                if any(k in msg for k in ("not found", "unknown command", "no such",
                                           "invalid input", "no command")):
                    logger.debug("命令 %s 不支持: %s", cmd, exc)
                    continue
                return ConfigCollectResult(status="error", error=f"命令执行失败 {cmd}: {exc}")
            if stderr_text and not output:
                # 命令失败输出到 stderr
                if any(k in stderr_text.lower() for k in ("not found", "unknown command",
                                                          "no such file", "command not found")):
                    logger.debug("命令 %s stderr 提示不支持: %s", cmd, stderr_text.strip())
                    continue
            if output and output.strip():
                full = output
                redacted = redact_config(full)
                return ConfigCollectResult(
                    status="ok",
                    full_text=full,
                    redacted=redacted,
                    full_hash=config_full_sha256(full),
                    truncated=truncated,
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

    一致性：
    - 去重基于 (device_id, config_full_hash) 唯一约束，并发重复采集只成功一次；
      唯一约束冲突时回退为「unchanged」返回，不产生新快照。
    - 快照保留上限：保留最新 MAX_SNAPSHOTS_PER_DEVICE 条，超出清理最旧的。
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
        password=password,          # P1: 修复已解密 SSH 密码未传入的问题
        key_pem=key_pem or "",
        vendor=device.vendor_platform,
        host_key_fingerprint=device.host_key_fingerprint,
        max_bytes=max_bytes,
    )
    if result.status != "ok":
        return {"status": result.status, "error": result.error}

    # 去重：同 hash 已存在则不重复入库（先查再插，唯一约束兜底并发）
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
        truncated=result.truncated,
    )
    try:
        db.add(snap)
        db.commit()
    except Exception as exc:  # noqa: BLE001 — 唯一约束冲突等
        db.rollback()
        # 并发写导致 (device_id, hash) 冲突：视为未变化
        again = (
            db.query(DeviceConfigSnapshot)
            .filter(
                DeviceConfigSnapshot.device_id == device.id,
                DeviceConfigSnapshot.config_full_hash == result.full_hash,
            )
            .first()
        )
        if again:
            return {
                "status": "unchanged",
                "snapshot_id": again.id,
                "hash": result.full_hash,
                "device_id": device.id,
            }
        logger.warning("配置快照写入失败 device=%s: %s", device.id, exc)
        return {"status": "error", "error": f"快照入库失败: {exc}"}
    db.refresh(snap)

    # 保留上限：清理超出 MAX_SNAPSHOTS_PER_DEVICE 的最旧快照
    _enforce_retention(db, device.id)

    # 登记 host key 指纹（首次采集）
    if result.host_key_fingerprint and device.host_key_fingerprint != result.host_key_fingerprint:
        device.host_key_fingerprint = result.host_key_fingerprint
        db.commit()

    # N4：配置变化事件与告警（changed=True 且已有历史快照时才登记）
    if changed:
        try:
            from app.services.config_change_alert import record_config_change_event
            record_config_change_event(db, device, snap)
        except Exception as exc:  # noqa: BLE001 — 事件登记失败不影响快照本身
            logger.warning("配置变化事件登记失败 device=%s: %s", device.id, exc)

    return {
        "status": "ok",
        "snapshot_id": snap.id,
        "changed": changed,
        "hash": result.full_hash,
        "command": result.command,
        "truncated": result.truncated,
        "device_id": device.id,
    }


def _enforce_retention(db: Session, device_id: int, keep: int | None = None) -> None:
    """清理超出保留上限的最旧快照。保留最新 keep 条（默认配置值）。"""
    from app.core.config import settings

    keep = keep or getattr(settings, "config_snapshot_retention", 20)
    all_snaps = (
        db.query(DeviceConfigSnapshot)
        .filter(DeviceConfigSnapshot.device_id == device_id)
        .order_by(DeviceConfigSnapshot.collected_at.desc(),
                  DeviceConfigSnapshot.id.desc())
        .all()
    )
    if len(all_snaps) <= keep:
        return
    excess = all_snaps[keep:]
    for old in excess:
        db.delete(old)
    if excess:
        db.commit()


@dataclass
class ConfigDiffLine:
    kind: str  # add / del / context
    old_line_no: int | None = None
    new_line_no: int | None = None
    text: str = ""


def diff_configs(old_text: str, new_text: str,
                 context_lines: int | None = None) -> list[dict]:
    """行级统一 diff（LCS），返回结构化变更行。

    context_lines: 每个变更块保留多少上下文行（None=全部，0=无上下文）。
    """
    import difflib

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    result: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            count = i2 - i1
            if context_lines is not None and count > context_lines:
                # 只保留该块的首尾 context_lines 行，中间省略
                keep_head = context_lines
                keep_tail = context_lines
                for k in range(i1, i1 + keep_head):
                    result.append({
                        "kind": "context",
                        "old_line_no": k + 1,
                        "new_line_no": j1 + (k - i1) + 1,
                        "text": old_lines[k],
                    })
                if count > keep_head + keep_tail:
                    result.append({
                        "kind": "skip",
                        "old_line_no": None,
                        "new_line_no": None,
                        "text": f"... {count - keep_head - keep_tail} 行省略 ...",
                    })
                for k in range(i2 - keep_tail, i2):
                    if k < i1 + keep_head:
                        continue
                    result.append({
                        "kind": "context",
                        "old_line_no": k + 1,
                        "new_line_no": j1 + (k - i1) + 1,
                        "text": old_lines[k],
                    })
            else:
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
    prefix = {"add": "+", "del": "-", "context": " ", "skip": "~"}
    return "\n".join(f"{prefix.get(d['kind'], ' ')}{d['text']}" for d in diff_lines)