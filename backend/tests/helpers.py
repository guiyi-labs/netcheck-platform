"""测试公共辅助函数。

巡检执行已改为异步：POST /api/tasks/{id}/run 返回 pending 运行并后台执行，
测试需要轮询运行状态直到终态。
"""
import time

from fastapi.testclient import TestClient

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def wait_run(client: TestClient, headers: dict[str, str], run_id: int, timeout: float = 15.0) -> dict:
    """轮询 GET /api/tasks/runs/{run_id} 直到运行进入终态，返回运行数据。"""
    deadline = time.time() + timeout
    last_status = "pending"
    while time.time() < deadline:
        resp = client.get(f"/api/tasks/runs/{run_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        last_status = data["status"]
        if last_status in TERMINAL_STATUSES:
            return data
        time.sleep(0.05)
    raise AssertionError(f"运行 {run_id} 未在 {timeout}s 内完成，最后状态 {last_status}")