from datetime import date, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.inspection import InspectionResult, InspectionRun, InspectionTask
from app.schemas.common import PageData, Response
from app.schemas.result import GlobalResultOut

router = APIRouter(
    prefix="/api/results",
    tags=["results"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=Response[PageData[GlobalResultOut]])
def list_global_results(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    run_id: int | None = None,
    task_id: int | None = None,
    asset_id: int | None = None,
    check_type: str | None = None,
    status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> Response[PageData[GlobalResultOut]]:
    q = db.query(InspectionResult, InspectionRun, InspectionTask, Asset).join(InspectionRun, InspectionResult.run_id == InspectionRun.id).join(InspectionTask, InspectionRun.task_id == InspectionTask.id).join(Asset, InspectionResult.asset_id == Asset.id)
    if run_id is not None:
        q = q.filter(InspectionResult.run_id == run_id)
    if task_id is not None:
        q = q.filter(InspectionRun.task_id == task_id)
    if asset_id is not None:
        q = q.filter(InspectionResult.asset_id == asset_id)
    if check_type:
        q = q.filter(InspectionResult.check_type == check_type)
    if status:
        q = q.filter(InspectionResult.status == status)
    if start_date is not None:
        q = q.filter(InspectionResult.checked_at >= date_to_start(start_date))
    if end_date is not None:
        q = q.filter(InspectionResult.checked_at <= date_to_end(end_date))
    total = q.count()
    rows = q.order_by(InspectionResult.checked_at.desc(), InspectionResult.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [
        GlobalResultOut(
            id=result.id,
            run_id=result.run_id,
            task_id=run.task_id,
            task_name=task.name,
            asset_id=result.asset_id,
            asset_name=asset.name,
            check_type=result.check_type,
            target=result.target,
            status=result.status,
            response_time=result.response_time,
            message=result.message,
            error_message=result.error_message,
            checked_at=result.checked_at,
        )
        for result, run, task, asset in rows
    ]
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=items))


def date_to_start(value: date):
    from datetime import datetime

    return datetime.combine(value, time.min)


def date_to_end(value: date):
    from datetime import datetime

    return datetime.combine(value, time.max)
