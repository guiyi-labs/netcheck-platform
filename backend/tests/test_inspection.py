import time

from fastapi.testclient import TestClient

from app.services.checkers import CheckResult
from app.services.checkers import CHECKERS as CHECKERS_IMPL

from helpers import wait_run


def set_checker(monkeypatch, check_type: str, checker) -> None:
    """替换检测器：worker 线程读取 app.services.checkers.CHECKERS 的同一字典对象。"""
    monkeypatch.setitem(CHECKERS_IMPL, check_type, checker)


def _poll_until(predicate, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("轮询条件未在超时时间内满足")


def test_tasks_require_token(client: TestClient):
    assert client.get("/api/tasks").status_code == 401


def test_create_update_toggle_and_run_history(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}
    created = client.post(
        "/api/tasks",
        headers=headers,
        json={
            "name": "测试巡检",
            "description": "检查演示资产",
            "check_types": ["ping", "port", "http"],
            "asset_ids": [1, 2],
            "enabled": True,
        },
    )
    assert created.status_code == 201
    task_id = created.json()["data"]["id"]

    updated = client.put(
        f"/api/tasks/{task_id}",
        headers=headers,
        json={
            "name": "测试巡检-改",
            "description": None,
            "check_types": ["ping"],
            "asset_ids": [1],
            "enabled": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "测试巡检-改"
    assert client.post(f"/api/tasks/{task_id}/disable", headers=headers).json()["data"]["enabled"] is False
    disabled_run = client.post(f"/api/tasks/{task_id}/run", headers=headers)
    assert disabled_run.status_code == 409
    assert disabled_run.json()["detail"] == "巡检任务已停用，无法执行"
    assert client.post(f"/api/tasks/{task_id}/enable", headers=headers).json()["data"]["enabled"] is True

    class FakeChecker:
        def check(self, asset):
            return [CheckResult("success", asset.ip, 12.5, "正常")]

    set_checker(monkeypatch, "ping", FakeChecker())
    run = client.post(f"/api/tasks/{task_id}/run", headers=headers)
    assert run.status_code == 200
    run_data = run.json()["data"]
    assert run_data["status"] == "pending"
    run_id = run_data["id"]
    finished = wait_run(client, headers, run_id)
    assert finished["status"] == "completed"

    history = client.get(f"/api/tasks/{task_id}/runs", headers=headers)
    assert history.status_code == 200
    assert history.json()["data"]["total"] == 1
    results = client.get(f"/api/tasks/runs/{run_id}/results", headers=headers)
    assert results.status_code == 200
    assert results.json()["data"]["items"][0]["status"] == "success"


def test_checker_error_is_stored_and_does_not_block_run(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "错误检查", "check_types": ["ping"], "asset_ids": [1, 2]},
    ).json()["data"]

    class FailingChecker:
        def check(self, asset):
            raise RuntimeError("network unavailable")

    set_checker(monkeypatch, "ping", FailingChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    wait_run(client, headers, run["id"])
    results = client.get(f"/api/tasks/runs/{run['id']}/results", headers=headers).json()["data"]
    assert results["total"] == 2
    assert all(item["error_message"] == "network unavailable" for item in results["items"])


def test_diagnosis_require_token(client: TestClient):
    assert client.get("/api/diagnosis").status_code == 401


def test_get_run_not_found(client: TestClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    assert client.get("/api/tasks/runs/999999", headers=headers).status_code == 404


def test_run_generates_http500_and_slow_diagnosis_and_updates_asset_status(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "诊断检查", "check_types": ["http"], "asset_ids": [1, 2]},
    ).json()["data"]

    class HttpChecker:
        def check(self, asset):
            if asset.id == 1:
                return [CheckResult("failed", f"http://{asset.ip}", 100, error_message="HTTP 500")]
            return [CheckResult("warning", f"http://{asset.ip}", 3000, "HTTP 200，响应缓慢")]

    set_checker(monkeypatch, "http", HttpChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    wait_run(client, headers, run["id"])

    diagnoses = client.get(f"/api/diagnosis/runs/{run['id']}", headers=headers)
    assert diagnoses.status_code == 200
    items = diagnoses.json()["data"]["items"]
    assert len(items) == 2
    assert {item["fault_type"] for item in items} == {"Web应用内部错误", "网络拥塞或服务性能下降"}
    assert {item["severity"] for item in items} == {"major", "warning"}
    assert client.get("/api/assets/1", headers=headers).json()["data"]["status"] == "warning"
    assert client.get("/api/assets/2", headers=headers).json()["data"]["status"] == "warning"


def test_ping_failed_updates_asset_offline(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "离线检查", "check_types": ["ping"], "asset_ids": [1]},
    ).json()["data"]

    class PingChecker:
        def check(self, asset):
            return [CheckResult("failed", asset.ip, 10, error_message="Ping 不可达")]

    set_checker(monkeypatch, "ping", PingChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    wait_run(client, headers, run["id"])
    assert client.get("/api/assets/1", headers=headers).json()["data"]["status"] == "offline"


def test_diagnosis_list_filters_detail_404_and_regenerate_idempotent(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "筛选检查", "check_types": ["http"], "asset_ids": [1, 2]},
    ).json()["data"]

    class HttpChecker:
        def check(self, asset):
            if asset.id == 1:
                return [CheckResult("failed", f"http://{asset.ip}", 80, error_message="HTTP 404")]
            return [CheckResult("failed", f"http://{asset.ip}", 90, error_message="HTTP 500")]

    set_checker(monkeypatch, "http", HttpChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    wait_run(client, headers, run["id"])

    filtered = client.get(
        "/api/diagnosis",
        headers=headers,
        params={"run_id": run["id"], "asset_id": 1, "severity": "minor", "check_type": "http", "fault_type": "请求路径或访问权限异常"},
    )
    assert filtered.status_code == 200
    data = filtered.json()["data"]
    assert data["total"] == 1
    diagnosis_id = data["items"][0]["id"]
    assert client.get(f"/api/diagnosis/{diagnosis_id}", headers=headers).json()["data"]["fault_type"] == "请求路径或访问权限异常"
    assert client.get("/api/diagnosis/999999", headers=headers).status_code == 404

    first_total = client.get(f"/api/diagnosis/runs/{run['id']}", headers=headers).json()["data"]["total"]
    regenerated = client.post(f"/api/diagnosis/runs/{run['id']}/generate", headers=headers)
    assert regenerated.status_code == 200
    assert regenerated.json()["data"]["total"] == first_total
    second_total = client.get(f"/api/diagnosis/runs/{run['id']}", headers=headers).json()["data"]["total"]
    assert second_total == first_total


def test_dns_task_generates_diagnosis(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "DNS检查", "check_types": ["dns"], "asset_ids": [1, 2]},
    ).json()["data"]

    class DnsChecker:
        def check(self, asset):
            if asset.id == 1:
                return [CheckResult("failed", asset.hostname or asset.ip, 20, error_message="NXDOMAIN")]
            return [CheckResult("warning", asset.hostname or asset.ip, 3000, "DNS 解析成功，响应缓慢")]

    set_checker(monkeypatch, "dns", DnsChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    assert run["trigger_type"] == "manual"
    wait_run(client, headers, run["id"])

    diagnoses = client.get(f"/api/diagnosis/runs/{run['id']}", headers=headers).json()["data"]["items"]
    assert {item["fault_type"] for item in diagnoses} == {"DNS配置或解析服务异常", "DNS解析响应较慢"}
    assert {item["severity"] for item in diagnoses} == {"major", "warning"}


def test_scheduler_fields_status_and_scheduled_trigger(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}

    class PingChecker:
        def check(self, asset):
            return [CheckResult("success", asset.ip, 5, "正常")]

    set_checker(monkeypatch, "ping", PingChecker())
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={
            "name": "定时检查",
            "check_types": ["ping"],
            "asset_ids": [1],
            "schedule_enabled": True,
            "schedule_interval_minutes": 5,
        },
    )
    assert task.status_code == 201
    data = task.json()["data"]
    assert data["schedule_enabled"] is True
    assert data["schedule_interval_minutes"] == 5
    assert data["next_run_at"] is not None

    status_resp = client.get("/api/scheduler/status", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["running"] is True

    # 模拟定时触发：调度器入队一条 scheduled 运行，异步执行
    from app.services.scheduler import scheduler_service

    scheduler_service.scheduled_run_task(data["id"])
    _poll_until(
        lambda: client.get(f"/api/tasks/{data['id']}/runs", headers=headers).json()["data"]["total"] == 1
    )

    def latest_run():
        return client.get(f"/api/tasks/{data['id']}/runs", headers=headers).json()["data"]["items"][0]

    _poll_until(lambda: latest_run()["status"] in ("completed", "failed", "cancelled"))
    history = latest_run()
    assert history["trigger_type"] == "scheduled"
    assert history["status"] == "completed"