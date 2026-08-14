"""巡检执行器：后台线程 + 内存队列，避免巡检阻塞 API 请求。

设计：
- 手动/定时的「创建运行」只负责写入一条 pending 运行记录并入队。
- worker 线程取出运行后异步完成：检测 -> 诊断 -> 告警 -> 资产状态回写。
- 同一运行内不同资产的检测并行执行（ThreadPoolExecutor），单个资产内的
  多个检测类型串行，保证单资产结果写入顺序稳定。
- 前端通过 GET /api/tasks/runs/{run_id} 轮询运行状态。
"""
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.inspection import InspectionResult, InspectionRun, InspectionTask
from app.services.alerts import evaluate_alerts
from app.services.checkers import CHECKERS
from app.services.diagnosis import generate_diagnoses, update_asset_statuses

logger = logging.getLogger("netcheck.executor")

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

_run_queue: queue.Queue[int | None] = queue.Queue()
_worker: threading.Thread | None = None
_stop = threading.Event()
_started = False


def start() -> None:
    """启动 worker 线程（幂等）。"""
    global _worker, _started
    if _started and _worker is not None and _worker.is_alive():
        return
    _stop.clear()
    _worker = threading.Thread(target=_worker_loop, name="netcheck-executor", daemon=True)
    _worker.start()
    _started = True


def shutdown() -> None:
    """停止 worker：先排空队列（join），再退出线程。"""
    global _started
    if not _started:
        return
    _stop.set()
    _run_queue.put(None)
    if _worker is not None:
        try:
            _run_queue.join()
        except Exception:
            pass
        _worker.join(timeout=15)
    _started = False


def enqueue_task_run(task_id: int, trigger_type: str = "manual") -> int:
    """创建 pending 运行记录并入队，返回 run_id。"""
    db = SessionLocal()
    try:
        run = InspectionRun(task_id=task_id, status="pending", trigger_type=trigger_type)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()
    submit_run(run_id)
    return run_id


def submit_run(run_id: int) -> None:
    _run_queue.put(run_id)


def _worker_loop() -> None:
    while not _stop.is_set():
        try:
            run_id = _run_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            if run_id is not None:
                process_run(run_id)
        except Exception:
            logger.exception("巡检运行 %s 处理异常", run_id)
        finally:
            _run_queue.task_done()


def _next_run_at(task: InspectionTask) -> datetime | None:
    if not task.enabled or not task.schedule_enabled or not task.schedule_interval_minutes:
        return None
    return datetime.now() + timedelta(minutes=task.schedule_interval_minutes)


def _execute_checks(run: InspectionRun, task: InspectionTask, db) -> None:
    check_types = [item for item in task.check_types.split(",") if item]
    # 只把纯数据交给检测线程：SQLAlchemy Session/ORM 实例不能跨线程共享，
    # 线程只读资产标量字段并返回纯字典，由主线程统一构造 ORM 对象。
    plain_assets = [
        {
            "asset_id": asset.id,
            "ip": asset.ip,
            "hostname": asset.hostname,
            "ports": asset.ports,
        }
        for asset in task.assets
    ]

    def run_asset(plain: dict) -> list[dict]:
        asset = SimpleNamespace(
            id=plain["asset_id"],
            ip=plain["ip"],
            hostname=plain["hostname"],
            ports=plain["ports"],
        )
        rows: list[dict] = []
        for check_type in check_types:
            checker = CHECKERS.get(check_type)
            if checker is None:
                continue
            try:
                for result in checker.check(asset):
                    rows.append(
                        {
                            "asset_id": asset.id,
                            "check_type": check_type,
                            "target": result.target,
                            "status": result.status,
                            "response_time": result.response_time,
                            "message": result.message,
                            "error_message": result.error_message,
                        }
                    )
            except Exception as exc:
                rows.append({"asset_id": asset.id, "check_type": check_type, "status": "failed", "error_message": str(exc)})
        return rows

    all_rows: list[dict] = []
    if settings.check_concurrency <= 1 or len(plain_assets) <= 1:
        for plain in plain_assets:
            all_rows.extend(run_asset(plain))
    else:
        workers = min(settings.check_concurrency, len(plain_assets))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="check") as pool:
            futures = [pool.submit(run_asset, plain) for plain in plain_assets]
            for future in as_completed(futures):
                all_rows.extend(future.result())
    for row in all_rows:
        db.add(InspectionResult(run_id=run.id, **row))
    db.commit()


def process_run(run_id: int) -> None:
    """完整处理一次运行。由 worker 线程调用，使用独立数据库会话。"""
    db = SessionLocal()
    try:
        run = db.get(InspectionRun, run_id)
        if run is None or run.status != "pending":
            return
        task = (
            db.query(InspectionTask)
            .options(selectinload(InspectionTask.assets))
            .filter(InspectionTask.id == run.task_id)
            .first()
        )
        if task is None or not task.enabled:
            run.status = "failed"
            run.error_message = "巡检任务不存在或已停用"
            run.finished_at = datetime.now()
            db.commit()
            return
        run.status = "running"
        db.commit()

        _execute_checks(run, task, db)

        # 先完成诊断、告警、资产状态回写，再标记运行完成；否则轮询方会在
        # 后处理尚未落库时就看到 completed，导致竞态（原先同步执行无此问题）。
        generate_diagnoses(run.id, db)
        evaluate_alerts(run.id, db)
        update_asset_statuses(run.id, db)

        run.status = "completed"
        run.finished_at = datetime.now()
        if run.trigger_type == "scheduled":
            task.last_scheduled_run_at = run.finished_at
            task.next_run_at = _next_run_at(task)
        db.commit()

        # 告警通知分发放到运行完成之后（B 阶段完善；未启用时为空操作）
        try:
            from app.services.notifications import dispatch_alert_notifications

            dispatch_alert_notifications(run.id, db)
        except Exception:
            logger.exception("运行 %s 告警通知分发失败", run.id)
    except Exception:
        logger.exception("巡检运行 %s 执行失败", run_id)
        try:
            run.status = "failed"
            run.error_message = "执行过程发生异常"
            run.finished_at = datetime.now()
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()