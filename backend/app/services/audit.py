"""操作审计服务：统一记录关键操作日志，供审计查询与管理。"""
from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import OperationLog


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def record(
    db: Session,
    username: str,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: str | None = None,
    request: Request | None = None,
) -> None:
    """写入一条操作日志，随当前会话一起提交（由调用方负责 commit 时机）。"""
    log = OperationLog(
        username=username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip=_client_ip(request),
    )
    db.add(log)