"""B3 任务控制：取消执行、失败重试、Cron 调度。"""
import time

from fastapi.testclient import TestClient

from app.services.checkers import CheckResult, CHECKERS

from helpers import wait_run


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_cancel_pending_running_run(client: TestClient, auth_token: str, monkeypatch):
    headers = _h(auth_token)

    class SlowChecker:
        def check(self, asset):
            time.sleep(0.15)
            return [CheckResult("success", asset.ip, 1, "ok")]

    monkeypatch.setitem(CHECKERS, "ping", SlowChecker())
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "取消测试", "check_types": ["ping"], "asset_ids": [1, 2, 3]},
    ).json()["data"]
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]

    # 立即请求取消（运行大概率仍在 running）
    cancelled = client.post(f"/api/tasks/runs/{run['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    data = cancelled.json()["data"]
    assert data["cancel_requested"] is True

    # 运行最终进入 cancelled（或 completed 并发窗口极小，这里只断言终态之一）
    final = wait_run(client, headers, run["id"])
    assert final["status"] in ("cancelled", "completed")

    # 已结束的运行不能再取消
    again = client.post(f"/api/tasks/runs/{run['id']}/cancel", headers=headers)
    assert again.status_code == 409

    # 取消不存在的运行
    assert client.post("/api/tasks/runs/999999/cancel", headers=headers).status_code == 404


def test_retry_failed_run_creates_new_run(client: TestClient, auth_token: str, monkeypatch):
    headers = _h(auth_token)

    class FailingChecker:
        def check(self, asset):
            raise RuntimeError("boom")

    monkeypatch.setitem(CHECKERS, "ping", FailingChecker())
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "重试测试", "check_types": ["ping"], "asset_ids": [1]},
    ).json()["data"]
    # 先停用任务，重试应被拒绝
    client.post(f"/api/tasks/{task['id']}/disable", headers=headers)
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers)
    assert run.status_code == 409
    client.post(f"/api/tasks/{task['id']}/enable", headers=headers)

    # 失败运行完成后重试
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    failed = wait_run(client, headers, run["id"])
    assert failed["status"] == "failed"

    retried = client.post(f"/api/tasks/runs/{run['id']}/retry", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["data"]["id"] != run["id"]
    new_run_id = retried.json()["data"]["id"]
    wait_run(client, headers, new_run_id)

    history = client.get(f"/api/tasks/{task['id']}/runs", headers=headers).json()["data"]
    assert history["total"] == 2


def test_cron_expression_task(client: TestClient, auth_token: str):
    headers = _h(auth_token)
    # 合法 Cron 创建
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={
            "name": "Cron任务",
            "check_types": ["ping"],
            "asset_ids": [1],
            "schedule_enabled": True,
            "schedule_cron": "0 */2 * * *",
            "schedule_interval_minutes": None,
        },
    )
    assert task.status_code == 201
    data = task.json()["data"]
    assert data["schedule_cron"] == "0 */2 * * *"
    assert data["next_run_at"] is not None

    # 非法 Cron 拒绝
    bad = client.post(
        "/api/tasks",
        headers=headers,
        json={
            "name": "坏Cron",
            "check_types": ["ping"],
            "asset_ids": [1],
            "schedule_enabled": True,
            "schedule_cron": "not-a-cron",
        },
    )
    assert bad.status_code == 422

    # 启用定时但两种触发器都没有 -> 422
    none_trigger = client.post(
        "/api/tasks",
        headers=headers,
        json={
            "name": "无触发器",
            "check_types": ["ping"],
            "asset_ids": [1],
            "schedule_enabled": True,
            "schedule_interval_minutes": None,
            "schedule_cron": None,
        },
    )
    assert none_trigger.status_code == 422

    # 调度器应已注册 cron 任务
    status_resp = client.get("/api/scheduler/status", headers=headers).json()["data"]
    assert status_resp["running"] is True