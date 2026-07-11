from fastapi.testclient import TestClient

from app.services.checkers import CheckResult


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

    monkeypatch.setitem(__import__("app.api.inspection", fromlist=["CHECKERS"]).CHECKERS, "ping", FakeChecker())
    run = client.post(f"/api/tasks/{task_id}/run", headers=headers)
    assert run.status_code == 200
    run_id = run.json()["data"]["id"]
    assert run.json()["data"]["status"] == "completed"

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

    monkeypatch.setitem(__import__("app.api.inspection", fromlist=["CHECKERS"]).CHECKERS, "ping", FailingChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    results = client.get(f"/api/tasks/runs/{run['id']}/results", headers=headers).json()["data"]
    assert results["total"] == 2
    assert all(item["error_message"] == "network unavailable" for item in results["items"])


def test_diagnosis_require_token(client: TestClient):
    assert client.get("/api/diagnosis").status_code == 401


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

    monkeypatch.setitem(__import__("app.api.inspection", fromlist=["CHECKERS"]).CHECKERS, "http", HttpChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]

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

    monkeypatch.setitem(__import__("app.api.inspection", fromlist=["CHECKERS"]).CHECKERS, "ping", PingChecker())
    client.post(f"/api/tasks/{task['id']}/run", headers=headers)
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

    monkeypatch.setitem(__import__("app.api.inspection", fromlist=["CHECKERS"]).CHECKERS, "http", HttpChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]

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

    monkeypatch.setitem(__import__("app.api.inspection", fromlist=["CHECKERS"]).CHECKERS, "dns", DnsChecker())
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    assert run["trigger_type"] == "manual"

    diagnoses = client.get(f"/api/diagnosis/runs/{run['id']}", headers=headers).json()["data"]["items"]
    assert {item["fault_type"] for item in diagnoses} == {"DNS配置或解析服务异常", "DNS解析响应较慢"}
    assert {item["severity"] for item in diagnoses} == {"major", "warning"}


def test_scheduler_fields_status_and_scheduled_trigger(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}

    class PingChecker:
        def check(self, asset):
            return [CheckResult("success", asset.ip, 5, "正常")]

    monkeypatch.setitem(__import__("app.api.inspection", fromlist=["CHECKERS"]).CHECKERS, "ping", PingChecker())
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

    from app.api.inspection import execute_task_run, get_task
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        run = execute_task_run(get_task(data["id"], db), db, trigger_type="scheduled")
        assert run.trigger_type == "scheduled"
    finally:
        db.close()

    history = client.get(f"/api/tasks/{data['id']}/runs", headers=headers).json()["data"]["items"]
    assert history[0]["trigger_type"] == "scheduled"
