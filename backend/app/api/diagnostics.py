"""网络诊断接口：traceroute 等交互式排障工具。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import Response
from app.services.traceroute import MAX_HOPS_DEFAULT, WAIT_DEFAULT, run_traceroute

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"], dependencies=[Depends(get_current_user)])


@router.post("/traceroute", response_model=Response[dict])
def traceroute_diagnostic(
    target: str,
    max_hops: int = MAX_HOPS_DEFAULT,
    wait: float = WAIT_DEFAULT,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response[dict]:
    """对目标（IP 或主机名）执行 traceroute，返回逐跳路径。"""
    if not target.strip():
        raise HTTPException(status_code=422, detail="目标不能为空")
    if max_hops < 1 or max_hops > 64:
        raise HTTPException(status_code=422, detail="max_hops 必须在 1-64 之间")
    data = run_traceroute(target.strip(), max_hops=max_hops, wait=wait)
    return Response(
        message="Traceroute 完成" if data["status"] == "completed" else data.get("error") or "Traceroute 未到达目标",
        data=data,
    )