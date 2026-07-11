from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
from app.models.inspection import InspectionResult, InspectionRun, InspectionTask
from app.schemas.common import PageData, Response
from app.schemas.inspection import CHECK_TYPES, ResultOut, RunOut, TaskCreate, TaskOut, TaskUpdate
from app.services.alerts import evaluate_alerts
from app.services.checkers import CHECKERS
from app.services.diagnosis import generate_diagnoses, update_asset_statuses

router = APIRouter(
    prefix="/api/tasks",
    tags=["inspection"],
    dependencies=[Depends(get_current_user)],
)


def _next_run_at(task: InspectionTask) -> datetime | None:
    if not task.enabled or not task.schedule_enabled or not task.schedule_interval_minutes:
        return None
    return datetime.now() + timedelta(minutes=task.schedule_interval_minutes)


def _reload_task(task_id: int) -> None:
    from app.services.scheduler import scheduler_service

    scheduler_service.reload_task(task_id)


def task_out(task: InspectionTask) -> TaskOut:
    return TaskOut(
        id=task.id,
        name=task.name,
        description=task.description,
        check_types=task.check_types.split(","),
        asset_ids=[asset.id for asset in task.assets],
        enabled=task.enabled,
        schedule_enabled=task.schedule_enabled,
        schedule_interval_minutes=task.schedule_interval_minutes,
        next_run_at=task.next_run_at,
        last_scheduled_run_at=task.last_scheduled_run_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def get_task(task_id: int, db: Session) -> InspectionTask:
    task = (
        db.query(InspectionTask)
        .options(selectinload(InspectionTask.assets))
        .filter(InspectionTask.id == task_id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="巡检任务不存在")
    return task


def set_task_values(task: InspectionTask, payload: TaskCreate | TaskUpdate, db: Session) -> None:
    if not set(payload.check_types).issubset(CHECK_TYPES):
        raise HTTPException(status_code=422, detail="不支持的检测类型")
    if payload.schedule_enabled and not payload.schedule_interval_minutes:
        raise HTTPException(status_code=422, detail="启用定时巡检时必须设置间隔分钟数")
    assets = db.query(Asset).filter(Asset.id.in_(payload.asset_ids)).all()
    if len(assets) != len(set(payload.asset_ids)):
        raise HTTPException(status_code=422, detail="存在不存在的资产")
    task.name = payload.name
    task.description = payload.description
    task.check_types = ",".join(payload.check_types)
    task.enabled = payload.enabled
    task.schedule_enabled = payload.schedule_enabled
    task.schedule_interval_minutes = payload.schedule_interval_minutes
    task.next_run_at = _next_run_at(task)
    task.assets = assets


def execute_task_run(task: InspectionTask, db: Session, trigger_type: str = "manual") -> InspectionRun:
    if not task.enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="巡检任务已停用，无法执行")
    run = InspectionRun(task_id=task.id, status="running", trigger_type=trigger_type)
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        for asset in task.assets:
            for check_type in task.check_types.split(","):
                try:
                    for result in CHECKERS[check_type].check(asset):
                        db.add(InspectionResult(run_id=run.id, asset_id=asset.id, check_type=check_type, target=result.target, status=result.status, response_time=result.response_time, message=result.message, error_message=result.error_message))
                except Exception as exc:
                    db.add(InspectionResult(run_id=run.id, asset_id=asset.id, check_type=check_type, status="failed", error_message=str(exc)))
        run.status = "completed"
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
    run.finished_at = datetime.now()
    if trigger_type == "scheduled":
        task.last_scheduled_run_at = run.finished_at
        task.next_run_at = _next_run_at(task)
    db.commit()
    generate_diagnoses(run.id, db)
    evaluate_alerts(run.id, db)
    update_asset_statuses(run.id, db)
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=Response[PageData[TaskOut]])
def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Response[PageData[TaskOut]]:
    q = db.query(InspectionTask).options(selectinload(InspectionTask.assets))
    total = q.count()
    tasks = q.order_by(InspectionTask.id).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[task_out(task) for task in tasks]))


@router.post("", response_model=Response[TaskOut], status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Response[TaskOut]:
    task = InspectionTask()
    set_task_values(task, payload, db)
    db.add(task)
    db.commit()
    db.refresh(task)
    _reload_task(task.id)
    return Response(data=task_out(get_task(task.id, db)))


@router.get("/{task_id}", response_model=Response[TaskOut])
def get_task_detail(task_id: int, db: Session = Depends(get_db)) -> Response[TaskOut]:
    return Response(data=task_out(get_task(task_id, db)))


@router.put("/{task_id}", response_model=Response[TaskOut])
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> Response[TaskOut]:
    task = get_task(task_id, db)
    set_task_values(task, payload, db)
    db.commit()
    _reload_task(task_id)
    return Response(data=task_out(get_task(task_id, db)))


@router.post("/{task_id}/enable", response_model=Response[TaskOut])
def enable_task(task_id: int, db: Session = Depends(get_db)) -> Response[TaskOut]:
    task = get_task(task_id, db)
    task.enabled = True
    task.next_run_at = _next_run_at(task)
    db.commit()
    _reload_task(task_id)
    return Response(data=task_out(get_task(task_id, db)))


@router.post("/{task_id}/disable", response_model=Response[TaskOut])
def disable_task(task_id: int, db: Session = Depends(get_db)) -> Response[TaskOut]:
    task = get_task(task_id, db)
    task.enabled = False
    task.next_run_at = None
    db.commit()
    _reload_task(task_id)
    return Response(data=task_out(get_task(task_id, db)))


@router.post("/{task_id}/run", response_model=Response[RunOut])
def run_task(task_id: int, db: Session = Depends(get_db)) -> Response[RunOut]:
    run = execute_task_run(get_task(task_id, db), db, trigger_type="manual")
    return Response(data=RunOut.model_validate(run))


@router.get("/{task_id}/runs", response_model=Response[PageData[RunOut]])
def list_runs(task_id: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> Response[PageData[RunOut]]:
    get_task(task_id, db)
    q = db.query(InspectionRun).filter(InspectionRun.task_id == task_id)
    total = q.count()
    runs = q.order_by(InspectionRun.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[RunOut.model_validate(run) for run in runs]))


@router.get("/runs/{run_id}/results", response_model=Response[PageData[ResultOut]])
def list_results(run_id: int, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200), db: Session = Depends(get_db)) -> Response[PageData[ResultOut]]:
    if db.get(InspectionRun, run_id) is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    q = db.query(InspectionResult).filter(InspectionResult.run_id == run_id)
    total = q.count()
    results = q.order_by(InspectionResult.id).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[ResultOut.model_validate(result) for result in results]))
