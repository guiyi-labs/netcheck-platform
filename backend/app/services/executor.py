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
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.inspection import InspectionResult, InspectionRun, InspectionTask
from app.services.alerts import evaluate_alerts
from app.services.checkers import CHECKERS
from app.services.diagnosis import generate_diagnoses, update_asset_statuses
from app.services.execute_lock import acquire_lock, release_lock
from app.services.realtime import hub
from app.services.schedule import next_run_at

logger = logging.getLogger("netcheck.executor")

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

_run_queue: queue.Queue[int | None] = queue.Queue(maxsize=settings.run_queue_maxsize)
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
    """创建 pending 运行记录并入队，返回 run_id。

    队列满（run_queue_maxsize）时不排队，直接标记运行 failed，避免无限堆积。
    """
    db = SessionLocal()
    try:
        run = InspectionRun(task_id=task_id, status="pending", trigger_type=trigger_type)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()
    try:
        _run_queue.put_nowait(run_id)
    except queue.Full:
        _mark_queued_run_failed(run_id)
    return run_id


def _mark_queued_run_failed(run_id: int) -> None:
    """队列已满时立即将运行标记失败，由 API 层返回 429 语义（当前返回 200 + failed 运行）。"""
    db = SessionLocal()
    try:
        run = db.get(InspectionRun, run_id)
        if run is not None and run.status == "pending":
            run.status = "failed"
            run.error_message = "巡检执行队列已满，请稍后重试"
            run.finished_at = datetime.now()
            db.commit()
            _publish_run(run, "failed")
    finally:
        db.close()


def _publish_run(run, status: str) -> None:
    """向 WebSocket 推送一次运行状态变更（线程安全，可后台线程调用）。"""
    try:
        hub.publish(
            {
                "type": "run.updated",
                "run_id": run.id,
                "task_id": run.task_id,
                "status": status,
                "trigger_type": getattr(run, "trigger_type", None),
            }
        )
    except Exception:
        logger.debug("运行 %s 实况推送失败", run.id)


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
    return next_run_at(task.enabled and task.schedule_enabled, task.schedule_cron, task.schedule_interval_minutes)


def _cancel_requested(db, run_id: int) -> bool:
    row = db.query(InspectionRun.cancel_requested).filter(InspectionRun.id == run_id).scalar()
    return bool(row)


def _execute_checks(run: InspectionRun, task: InspectionTask, db) -> str:
    """执行一次运行的全部检测。

    返回运行结果状态：
    - "cancelled"：执行过程中收到取消请求，未持久化任何结果；
    - "failed"：全部检测结果均为失败（可整体重试）；
    - "ok"：至少有一条成功/警告结果。
    """
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
    cancelled = False
    if settings.check_concurrency <= 1 or len(plain_assets) <= 1:
        for plain in plain_assets:
            if cancelled:
                break
            all_rows.extend(run_asset(plain))
            cancelled = _cancel_requested(db, run.id)
    else:
        workers = min(settings.check_concurrency, len(plain_assets))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="check") as pool:
            futures = [pool.submit(run_asset, plain) for plain in plain_assets]
            for future in as_completed(futures):
                if not cancelled:
                    all_rows.extend(future.result())
                if not cancelled:
                    cancelled = _cancel_requested(db, run.id)
    if cancelled:
        return "cancelled"
    for row in all_rows:
        db.add(InspectionResult(run_id=run.id, **row))
    db.commit()
    if all_rows and all(row["status"] == "failed" for row in all_rows):
        return "failed"
    return "ok"


def process_run(run_id: int) -> None:
    """完整处理一次运行。由 worker 线程调用，使用独立数据库会话。"""
    db = SessionLocal()
    lock_held = False
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
        # 分布式执行锁：同一任务同一时刻只允许一个实例执行；
        # 拿不到锁说明另一实例/线程正在执行同任务（或锁未过期），标记失败而不是排队堆积。
        if not acquire_lock(db, task.id):
            run.status = "failed"
            run.error_message = "任务正在被其他实例执行，已跳过本次运行（分布式锁）"
            run.finished_at = datetime.now()
            db.commit()
            _publish_run(run, "failed")
            return
        lock_held = True
        run.status = "running"
        db.commit()
        _publish_run(run, "running")

        outcome = _execute_checks(run, task, db)
        if outcome == "cancelled":
            run.status = "cancelled"
            run.finished_at = datetime.now()
            db.commit()
            _publish_run(run, "cancelled")
            return
        if outcome == "failed":
            # 全部检测失败：仍执行诊断/告警以便观察，但运行整体标记为 failed 可重试
            generate_diagnoses(run.id, db)
            evaluate_alerts(run.id, db)
            update_asset_statuses(run.id, db)
            run.status = "failed"
            run.error_message = "全部检查项均失败"
            run.finished_at = datetime.now()
            db.commit()
            _publish_run(run, "failed")
            return

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
        _publish_run(run, "completed")

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
        if lock_held and run is not None:
            try:
                release_lock(db, run.task_id)
            except Exception:
                logger.exception("运行 %s 释放任务锁失败", run_id)
        db.close()