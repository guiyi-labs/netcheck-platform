"""密码哈希、固定 token 生成与登录安全工具。

使用标准库 hashlib 的 pbkdf2_sha256，不引入额外依赖，足够毕设场景。
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings


def utcnow() -> datetime:
    """返回不带时区信息的 UTC 当前时间，便于与 SQLite 存取的 naive datetime 比较。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    """生成 pbkdf2_sha256 哈希字符串，格式：pbkdf2_sha256$iterations$salt$digest"""
    salt = secrets.token_hex(16)
    iterations = 100_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations_str, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iterations_str)
        ).hex()
        return secrets.compare_digest(computed, digest)
    except (ValueError, AttributeError):
        return False


def generate_token() -> str:
    """生成 64 字符随机 token，作为固定会话令牌。"""
    return secrets.token_hex(32)


def token_expires_at() -> datetime:
    """根据配置的 token 有效期计算过期时间。"""
    return utcnow() + timedelta(hours=settings.token_ttl_hours)


def check_password_policy(password: str) -> str | None:
    """校验密码强度，返回错误信息；通过时返回 None。"""
    if len(password) < settings.password_min_length:
        return f"密码长度不能小于 {settings.password_min_length} 位"
    return None