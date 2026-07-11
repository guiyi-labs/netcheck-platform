from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.alert import Alert
from app.models.asset import Asset
from app.models.inspection import DiagnosisRecord, InspectionResult, InspectionRun, InspectionTask
from app.schemas.common import Response
from app.schemas.dashboard import DashboardCountItem, DashboardSummary, DashboardTrendItem, RecentAbnormalItem

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)


def _since_days(days: int) -> datetime:
    return datetime.now() - timedelta(days=days - 1)


@router.get("/summary", response_model=Response[DashboardSummary])
def get_summary(db: Session = Depends(get_db)) -> Response[DashboardSummary]:
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    data = DashboardSummary(
        asset_total=db.query(Asset).count(),
        online_assets=db.query(Asset).filter(Asset.status == "online").count(),
        offline_assets=db.query(Asset).filter(Asset.status == "offline").count(),
        warning_assets=db.query(Asset).filter(Asset.status == "warning").count(),
        unknown_assets=db.query(Asset).filter(Asset.status == "unknown").count(),
        task_total=db.query(InspectionTask).count(),
        run_total=db.query(InspectionRun).count(),
        today_runs=db.query(InspectionRun).filter(InspectionRun.started_at >= today_start).count(),
        today_abnormal_results=db.query(InspectionResult)
        .filter(InspectionResult.checked_at >= today_start, InspectionResult.status != "success")
        .count(),
        diagnosis_total=db.query(DiagnosisRecord).count(),
        active_alerts=db.query(Alert).filter(Alert.alert_status == "active").count(),
        unconfirmed_alerts=db.query(Alert).filter(Alert.alert_status == "active").count(),
        recovered_alerts_today=db.query(Alert).filter(Alert.alert_status == "recovered", Alert.recovered_at >= today_start).count(),
    )
    return Response(data=data)


@router.get("/asset-status", response_model=Response[list[DashboardCountItem]])
def get_asset_status(db: Session = Depends(get_db)) -> Response[list[DashboardCountItem]]:
    rows = db.query(Asset.status, func.count(Asset.id)).group_by(Asset.status).all()
    return Response(data=[DashboardCountItem(name=status or "unknown", count=count) for status, count in rows])


@router.get("/trend", response_model=Response[list[DashboardTrendItem]])
def get_trend(days: int = Query(7, ge=1, le=30), db: Session = Depends(get_db)) -> Response[list[DashboardTrendItem]]:
    start = _since_days(days).replace(hour=0, minute=0, second=0, microsecond=0)
    run_rows = db.query(func.date(InspectionRun.started_at), func.count(InspectionRun.id)).filter(InspectionRun.started_at >= start).group_by(func.date(InspectionRun.started_at)).all()
    abnormal_rows = db.query(func.date(InspectionResult.checked_at), func.count(InspectionResult.id)).filter(InspectionResult.checked_at >= start, InspectionResult.status != "success").group_by(func.date(InspectionResult.checked_at)).all()
    runs = {str(day): count for day, count in run_rows}
    abnormal = {str(day): count for day, count in abnormal_rows}
    items = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        items.append(DashboardTrendItem(date=day, runs=runs.get(day, 0), abnormal_results=abnormal.get(day, 0)))
    return Response(data=items)


@router.get("/fault-types", response_model=Response[list[DashboardCountItem]])
def get_fault_types(days: int = Query(7, ge=1, le=30), db: Session = Depends(get_db)) -> Response[list[DashboardCountItem]]:
    start = _since_days(days).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(DiagnosisRecord.fault_type, func.count(DiagnosisRecord.id)).filter(DiagnosisRecord.created_at >= start).group_by(DiagnosisRecord.fault_type).order_by(func.count(DiagnosisRecord.id).desc()).all()
    return Response(data=[DashboardCountItem(name=fault_type, count=count) for fault_type, count in rows])


@router.get("/recent-abnormal", response_model=Response[list[RecentAbnormalItem]])
def get_recent_abnormal(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)) -> Response[list[RecentAbnormalItem]]:
    rows = (
        db.query(InspectionResult, InspectionRun, InspectionTask, Asset)
        .join(InspectionRun, InspectionResult.run_id == InspectionRun.id)
        .join(InspectionTask, InspectionRun.task_id == InspectionTask.id)
        .join(Asset, InspectionResult.asset_id == Asset.id)
        .filter(InspectionResult.status != "success")
        .order_by(InspectionResult.checked_at.desc(), InspectionResult.id.desc())
        .limit(limit)
        .all()
    )
    items = [
        RecentAbnormalItem(
            id=result.id,
            run_id=result.run_id,
            task_id=run.task_id,
            task_name=task.name,
            asset_id=result.asset_id,
            asset_name=asset.name,
            check_type=result.check_type,
            status=result.status,
            target=result.target,
            message=result.message,
            error_message=result.error_message,
            checked_at=result.checked_at,
        )
        for result, run, task, asset in rows
    ]
    return Response(data=items)
