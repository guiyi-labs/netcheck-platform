"""登录失败限流（进程内实现）。

对「用户名 + 来源 IP」维度记录连续失败次数，超过阈值后锁定一段时间。
单进程部署场景足够；多实例部署时可替换为 Redis 计数。
"""
import threading
import time

from app.core.config import settings

_lock = threading.Lock()
# key -> {"failures": int, "locked_until": float 或 0}
_attempts: dict[str, dict] = {}


def _key(username: str, ip: str | None) -> str:
    return f"{username}@{ip or 'unknown'}"


def is_locked(username: str, ip: str | None) -> bool:
    with _lock:
        record = _attempts.get(_key(username, ip))
        if not record:
            return False
        if record["locked_until"] and record["locked_until"] > time.time():
            return True
        if record["locked_until"] and record["locked_until"] <= time.time():
            # 锁定期已过，重置
            del _attempts[_key(username, ip)]
        return False


def remaining_lock_seconds(username: str, ip: str | None) -> int:
    with _lock:
        record = _attempts.get(_key(username, ip))
        if record and record["locked_until"] > time.time():
            return int(record["locked_until"] - time.time())
        return 0


def record_failure(username: str, ip: str | None) -> None:
    key = _key(username, ip)
    with _lock:
        record = _attempts.setdefault(key, {"failures": 0, "locked_until": 0})
        record["failures"] += 1
        if record["failures"] >= settings.login_max_attempts:
            record["locked_until"] = time.time() + settings.login_lock_minutes * 60
            record["failures"] = 0


def reset_failures(username: str, ip: str | None) -> None:
    with _lock:
        _attempts.pop(_key(username, ip), None)


def reset_all_failures() -> None:
    """清空全部限流状态（测试或运维手动解锁使用）。"""
    with _lock:
        _attempts.clear()