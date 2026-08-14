"""趋势统计 API：为前端 ECharts 提供 RTT 曲线 / 可用率 SLA / 运行耗时数据。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.inspection import InspectionResult, InspectionRun, InspectionTask
from app.schemas.common import Response
from app.schemas.stats import AvailabilityItem, RttTrendItem, RunDurationItem, StatAssetItem

router = APIRouter(
    prefix="/api/stats",
    tags=["stats"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/assets", response_model=Response[list[StatAssetItem]])
def list_stat_assets(db: Session = Depends(get_db)) -> Response[list[StatAssetItem]]:
    rows = db.query(Asset).order_by(Asset.id).all()
    return Response(data=[StatAssetItem(id=asset.id, name=asset.name, ip=asset.ip) for asset in rows])


@router.get("/rtt-trend", response_model=Response[list[RttTrendItem]])
def rtt_trend(
    asset_id: int = Query(...),
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> Response[list[RttTrendItem]]:
    """指定资产每日平均/最大响应耗时（ms），用于网络延迟趋势曲线。"""
    start = (datetime.now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(
            func.date(InspectionResult.checked_at),
            func.avg(InspectionResult.response_time),
            func.max(InspectionResult.response_time),
        )
        .filter(
            InspectionResult.asset_id == asset_id,
            InspectionResult.checked_at >= start,
            InspectionResult.response_time.isnot(None),
        )
        .group_by(func.date(InspectionResult.checked_at))
        .all()
    )
    by_day = {str(day): (avg, max) for day, avg, max in rows}
    items = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        pair = by_day.get(day)
        if pair is None:
            items.append(RttTrendItem(date=day, avg_response_ms=None, max_response_ms=None))
        else:
            items.append(RttTrendItem(date=day, avg_response_ms=round(pair[0], 2), max_response_ms=round(pair[1], 2)))
    return Response(data=items)


@router.get("/availability", response_model=Response[list[AvailabilityItem]])
def availability(
    asset_id: int = Query(...),
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> Response[list[AvailabilityItem]]:
    """指定资产每日可用率（success 占比），用于 SLA 视图。"""
    start = (datetime.now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(
            func.date(InspectionResult.checked_at),
            func.count(InspectionResult.id),
            func.sum(func.cast(InspectionResult.status == "success", Integer)),
        )
        .filter(InspectionResult.asset_id == asset_id, InspectionResult.checked_at >= start)
        .group_by(func.date(InspectionResult.checked_at))
        .all()
    )
    by_day = {str(day): (total, success) for day, total, success in rows}
    items = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        pair = by_day.get(day)
        if pair is None:
            items.append(AvailabilityItem(date=day, total=0, success=0, rate=0.0))
        else:
            total, success = pair
            items.append(AvailabilityItem(date=day, total=total or 0, success=success or 0, rate=round((success or 0) / total * 100, 2) if total else 0.0))
    return Response(data=items)


@router.get("/run-durations", response_model=Response[list[RunDurationItem]])
def run_durations(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> Response[list[RunDurationItem]]:
    """最近运行的耗时（秒），用于运行时长趋势柱状图。"""
    start = (datetime.now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(InspectionRun, InspectionTask)
        .join(InspectionTask, InspectionRun.task_id == InspectionTask.id)
        .filter(
            InspectionRun.started_at >= start,
            InspectionRun.finished_at.isnot(None),
            InspectionRun.status.in_(["completed", "failed", "cancelled"]),
        )
        .order_by(InspectionRun.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for run, task in reversed(rows):
        duration = None
        if run.started_at is not None and run.finished_at is not None:
            duration = round((run.finished_at - run.started_at).total_seconds(), 2)
        items.append(
            RunDurationItem(
                run_id=run.id,
                task_id=task.id,
                task_name=task.name,
                started_at=run.started_at.isoformat() if run.started_at else None,
                duration_s=duration,
                status=run.status,
            )
        )
    return Response(data=items)