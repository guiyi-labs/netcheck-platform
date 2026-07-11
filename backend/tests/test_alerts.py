from fastapi.testclient import TestClient

from app.services.checkers import CheckResult


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def set_checker(monkeypatch, status: str, response_time: float = 10, message: str | None = None, error_message: str | None = None) -> None:
    class FakeChecker:
        def check(self, asset):
            return [CheckResult(status, asset.ip, response_time, message, error_message)]

    monkeypatch.setitem(__import__("app.api.inspection", fromlist=["CHECKERS"]).CHECKERS, "ping", FakeChecker())


def create_task(client: TestClient, auth_token: str) -> int:
    resp = client.post(
        "/api/tasks",
        headers=headers(auth_token),
        json={"name": "告警闭环检查", "check_types": ["ping"], "asset_ids": [1]},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


def run_task(client: TestClient, auth_token: str, task_id: int) -> int:
    resp = client.post(f"/api/tasks/{task_id}/run", headers=headers(auth_token))
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


def list_alerts(client: TestClient, auth_token: str, **params):
    resp = client.get("/api/alerts", headers=headers(auth_token), params=params)
    assert resp.status_code == 200
    return resp.json()["data"]


def test_alerts_require_token(client: TestClient):
    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/alerts/summary").status_code == 401
    assert client.get("/api/alert-policy").status_code == 401


def test_alert_policy_read_and_update(client: TestClient, auth_token: str):
    policy = client.get("/api/alert-policy", headers=headers(auth_token))
    assert policy.status_code == 200
    data = policy.json()["data"]
    assert data["failure_threshold"] == 3
    assert data["recovery_threshold"] == 2
    assert data["slow_response_threshold"] == 2000
    assert data["deduplicate_enabled"] is True

    updated = client.put(
        "/api/alert-policy",
        headers=headers(auth_token),
        json={"failure_threshold": 2, "recovery_threshold": 3, "enabled": False, "name": "自定义告警策略"},
    )
    assert updated.status_code == 200
    data = updated.json()["data"]
    assert data["name"] == "自定义告警策略"
    assert data["failure_threshold"] == 2
    assert data["recovery_threshold"] == 3
    assert data["enabled"] is False


def test_failure_threshold_third_failure_creates_alert_and_deduplicate_updates_trigger_count(client: TestClient, auth_token: str, monkeypatch):
    h = headers(auth_token)
    client.put("/api/alert-policy", headers=h, json={"failure_threshold": 3, "recovery_threshold": 2})
    task_id = create_task(client, auth_token)
    set_checker(monkeypatch, "failed", error_message="Ping 不可达")

    run_task(client, auth_token, task_id)
    assert list_alerts(client, auth_token)["total"] == 0
    run_task(client, auth_token, task_id)
    assert list_alerts(client, auth_token)["total"] == 0
    run_task(client, auth_token, task_id)
    alerts = list_alerts(client, auth_token)
    assert alerts["total"] == 1
    alert = alerts["items"][0]
    assert alert["alert_status"] == "active"
    assert alert["alert_key"] == "1:ping:主机离线或链路异常"
    assert alert["trigger_count"] == 1
    assert alert["consecutive_failures"] == 3

    run_task(client, auth_token, task_id)
    alerts = list_alerts(client, auth_token)
    assert alerts["total"] == 1
    assert alerts["items"][0]["id"] == alert["id"]
    assert alerts["items"][0]["trigger_count"] == 2
    assert alerts["items"][0]["consecutive_failures"] == 4


def test_confirm_and_auto_recover_after_two_successes(client: TestClient, auth_token: str, monkeypatch):
    h = headers(auth_token)
    client.put("/api/alert-policy", headers=h, json={"failure_threshold": 3, "recovery_threshold": 2})
    task_id = create_task(client, auth_token)
    set_checker(monkeypatch, "failed", error_message="Ping 不可达")
    for _ in range(3):
        run_task(client, auth_token, task_id)
    alert = list_alerts(client, auth_token)["items"][0]

    confirmed = client.post(f"/api/alerts/{alert['id']}/confirm", headers=h)
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["alert_status"] == "confirmed"
    assert confirmed.json()["data"]["confirmed_by"] == "admin"

    set_checker(monkeypatch, "success", message="正常")
    run_task(client, auth_token, task_id)
    assert client.get(f"/api/alerts/{alert['id']}", headers=h).json()["data"]["alert_status"] == "confirmed"
    run_task(client, auth_token, task_id)
    recovered = client.get(f"/api/alerts/{alert['id']}", headers=h).json()["data"]
    assert recovered["alert_status"] == "recovered"
    assert recovered["recovery_reason"] == "连续正常自动恢复"
    assert recovered["consecutive_successes"] == 2


def test_manual_recover_list_filters_and_dashboard_counts(client: TestClient, auth_token: str, monkeypatch):
    h = headers(auth_token)
    client.put("/api/alert-policy", headers=h, json={"failure_threshold": 3, "recovery_threshold": 2})
    task_id = create_task(client, auth_token)
    set_checker(monkeypatch, "failed", error_message="Ping 不可达")
    for _ in range(3):
        run_task(client, auth_token, task_id)
    alert = list_alerts(client, auth_token)["items"][0]

    filtered = list_alerts(client, auth_token, alert_status="active", asset_id=1, check_type="ping", fault_type="主机离线或链路异常")
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == alert["id"]

    summary = client.get("/api/dashboard/summary", headers=h).json()["data"]
    assert summary["active_alerts"] == 1
    assert summary["unconfirmed_alerts"] == 1
    assert summary["recovered_alerts_today"] == 0

    recovered = client.post(f"/api/alerts/{alert['id']}/recover", headers=h, json={"recovery_reason": "人工确认恢复"})
    assert recovered.status_code == 200
    assert recovered.json()["data"]["alert_status"] == "recovered"
    assert recovered.json()["data"]["recovery_reason"] == "人工确认恢复"

    active = list_alerts(client, auth_token, alert_status="active")
    assert active["total"] == 0
    recovered_list = list_alerts(client, auth_token, alert_status="recovered")
    assert recovered_list["total"] == 1

    alert_summary = client.get("/api/alerts/summary", headers=h).json()["data"]
    assert alert_summary["active_alerts"] == 0
    assert alert_summary["unconfirmed_alerts"] == 0
    assert alert_summary["recovered_alerts_today"] == 1
    dashboard = client.get("/api/dashboard/summary", headers=h).json()["data"]
    assert dashboard["active_alerts"] == 0
    assert dashboard["unconfirmed_alerts"] == 0
    assert dashboard["recovered_alerts_today"] == 1
