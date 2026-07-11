"""密码哈希与固定 token 生成。

使用标准库 hashlib 的 pbkdf2_sha256，不引入额外依赖，足够毕设场景。
"""
import hashlib
import secrets


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
