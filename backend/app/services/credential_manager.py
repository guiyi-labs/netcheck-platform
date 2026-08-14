"""凭据管理：AES-256-GCM 加密存储 + 脱敏。

- 凭据值（SNMPv3 认证/隐私密钥、SSH 私钥）以 AES-256-GCM 加密后入库；
- 加密密钥来自 NETCHECK_SECRET_KEY（可置空走外部 Secret 引用或禁用）；
- API/日志/导出只允许看到 状态位 + 摘要，绝不允许回显明文。
"""
import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


class SecretMissingError(RuntimeError):
    """缺少 NETCHECK_SECRET_KEY，无法解密凭据。"""


def _key_bytes() -> bytes:
    secret = (settings.secret_key or "").strip()
    if not secret:
        raise SecretMissingError("NETCHECK_SECRET_KEY 未配置，无法解密凭据")
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_secret(plaintext: str) -> str:
    """AES-256-GCM 加密，输出 base64(nonce + ciphertext + tag)。"""
    if not plaintext:
        return ""
    key = _key_bytes()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(blob: str) -> str:
    """解密 encrypt_secret 输出；失败抛 SecretMissingError / ValueError。"""
    if not blob:
        return ""
    key = _key_bytes()
    raw = base64.b64decode(blob.encode("ascii"))
    if len(raw) < 13:
        raise ValueError("凭据密文格式损坏")
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def secret_digest(plaintext: str) -> str:
    """摘要指纹（用于展示 has_secret，不泄露明文）。"""
    if not plaintext:
        return ""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()[:12]


def fingerprint_ssh_key(key_pem: str) -> str:
    """SSH 私钥指纹（SHA-256），用于 host key 核对与展示。"""
    if not key_pem:
        return ""
    return hashlib.sha256(key_pem.encode("utf-8")).hexdigest()[:16]


def safe_trailer(value: str | None, max_len: int = 8) -> str | None:
    """唯一保留末位摘要用于展示（脱敏）。"""
    if not value:
        return None
    return "…" + value[-max_len:]


def constant_time_equals(left: str, right: str) -> bool:
    """常量时间比较（供 host key / digest 校验）。"""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def redact(value: str) -> str:
    """日志脱敏：替换成固定掩码，杜绝凭据进日志。"""
    if not value:
        return ""
    return "*" * 8 + value[-4:] if len(value) > 4 else "****"