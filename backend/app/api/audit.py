from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.audit import OperationLog
from app.schemas.audit import AuditLogOut
from app.schemas.common import PageData, Response

router = APIRouter(
    prefix="/api/audit-logs",
    tags=["audit"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=Response[PageData[AuditLogOut]])
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    username: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> Response[PageData[AuditLogOut]]:
    q = db.query(OperationLog)
    if username:
        q = q.filter(OperationLog.username == username)
    if action:
        q = q.filter(OperationLog.action == action)
    if target_type:
        q = q.filter(OperationLog.target_type == target_type)
    if start_date is not None:
        q = q.filter(OperationLog.created_at >= datetime.combine(start_date, time.min))
    if end_date is not None:
        q = q.filter(OperationLog.created_at <= datetime.combine(end_date, time.max))
    total = q.count()
    logs = q.order_by(OperationLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[AuditLogOut.model_validate(log) for log in logs]))