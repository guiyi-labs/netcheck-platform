"""D4 分布式执行锁 + D5 有界执行队列。"""
import queue

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.services import executor
from app.services.checkers import CheckResult, CHECKERS
from app.services.execute_lock import acquire_lock, release_lock, worker_id

from helpers import wait_run


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_distributed_lock_prevents_duplicate_run(client: TestClient, auth_token: str):
    headers = _h(auth_token)
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "锁测试", "check_types": ["ping"], "asset_ids": [1]},
    ).json()["data"]
    task_id = task["id"]

    # 模拟「另一个实例」已持有该任务的锁
    db = SessionLocal()
    try:
        assert acquire_lock(db, task_id) is True
    finally:
        db.close()

    # 当前 worker 尝试执行同任务 → acquire_lock 应失败 → 运行标记 failed
    run = client.post(f"/api/tasks/{task_id}/run", headers=headers).json()["data"]
    final = wait_run(client, headers, run["id"])
    assert final["status"] == "failed"
    assert "分布式锁" in (final["error_message"] or "")

    # 释放锁后重试可成功
    db = SessionLocal()
    try:
        release_lock(db, task_id)
    finally:
        db.close()
    retried = client.post(f"/api/tasks/runs/{run['id']}/retry", headers=headers).json()["data"]
    final2 = wait_run(client, headers, retried["id"])
    assert final2["status"] in ("completed", "failed")


def test_queue_full_marks_run_failed(client: TestClient, auth_token: str, monkeypatch):
    headers = _h(auth_token)
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "队列测试", "check_types": ["ping"], "asset_ids": [1]},
    ).json()["data"]

    class FullQueue:
        def put_nowait(self, _item):
            raise queue.Full

    monkeypatch.setattr(executor, "_run_queue", FullQueue())
    run_id = executor.enqueue_task_run(task["id"], trigger_type="manual")
    db = SessionLocal()
    try:
        run = db.get(executor.InspectionRun, run_id)
    finally:
        db.close()
    assert run is not None
    assert run.status == "failed"
    assert "队列已满" in (run.error_message or "")


def test_lock_acquire_release_cycle(client: TestClient, auth_token: str):
    headers = _h(auth_token)
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "锁周期", "check_types": ["ping"], "asset_ids": [1]},
    ).json()["data"]
    task_id = task["id"]

    db = SessionLocal()
    try:
        assert acquire_lock(db, task_id) is True
        # 同任务重复加锁（未过期）应失败
        assert acquire_lock(db, task_id) is False
        release_lock(db, task_id)
        # 释放后可再次加锁
        assert acquire_lock(db, task_id) is True
        release_lock(db, task_id)
    finally:
        db.close()