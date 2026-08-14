"""分布式执行锁：多实例后端共享数据库时，防止同一巡检任务被并发重复执行。

- 加锁：任务首次加锁 / 锁已过期可抢占 / 未过期且非本人持有则加锁失败；
- 释放：任务正常结束或异常退出后由执行器调用 release_lock；
- 适用：MySQL 等多实例共享库；SQLite 单文件下本锁退化为无操作安全性保障。
"""
import os
import socket
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.inspection import TaskLock

LOCK_TTL_SECONDS = 600


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def acquire_lock(db: Session, task_id: int, ttl_seconds: int = LOCK_TTL_SECONDS) -> bool:
    """尝试为 task 加锁；成功返回 True，锁被他人持有返回 False。"""
    now = utcnow()
    lock = db.get(TaskLock, task_id)
    if lock is None:
        db.add(TaskLock(task_id=task_id, worker_id=worker_id(), expires_at=now + timedelta(seconds=ttl_seconds)))
        db.commit()
        return True
    if lock.expires_at <= now:
        lock.worker_id = worker_id()
        lock.acquired_at = now
        lock.expires_at = now + timedelta(seconds=ttl_seconds)
        db.commit()
        return True
    return False


def release_lock(db: Session, task_id: int) -> None:
    """任务结束后释放锁：只删除本实例持有的锁或已过期的锁。"""
    now = utcnow()
    lock = db.get(TaskLock, task_id)
    if lock is None:
        return
    if lock.worker_id == worker_id() or lock.expires_at <= now:
        db.delete(lock)
        db.commit()