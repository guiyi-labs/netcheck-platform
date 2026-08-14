"""审计日志：查询接口与关键操作落库。"""
from fastapi.testclient import TestClient


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_audit_logs_require_token(client: TestClient):
    assert client.get("/api/audit-logs").status_code == 401


def test_mutations_are_recorded_and_queryable(client: TestClient, auth_token: str):
    h = _headers(auth_token)
    # 登录本身应有一条 auth.login 记录
    logs = client.get("/api/audit-logs", headers=h).json()["data"]
    assert logs["total"] >= 1

    created = client.post("/api/assets", headers=h, json={"name": "审计资产", "ip": "10.0.0.99", "asset_type": "server"})
    assert created.status_code == 201
    asset_id = created.json()["data"]["id"]

    task = client.post("/api/tasks", headers=h, json={"name": "审计任务", "check_types": ["ping"], "asset_ids": [asset_id]})
    assert task.status_code == 201
    task_id = task.json()["data"]["id"]

    logs = client.get("/api/audit-logs", headers=h).json()["data"]["items"]
    actions = [log["action"] for log in logs]
    assert "asset.create" in actions
    assert "task.create" in actions
    assert "auth.login" in actions

    created_log = next(log for log in logs if log["action"] == "asset.create")
    assert created_log["username"] == "admin"
    assert created_log["target_type"] == "asset"
    assert created_log["target_id"] == asset_id

    filtered = client.get("/api/audit-logs", headers=h, params={"action": "task.create"}).json()["data"]
    assert filtered["total"] == 1

    by_user = client.get("/api/audit-logs", headers=h, params={"username": "admin"}).json()["data"]
    assert by_user["total"] >= 3


def test_audit_pagination(client: TestClient, auth_token: str):
    h = _headers(auth_token)
    for i in range(3):
        client.post("/api/assets", headers=h, json={"name": f"分页-{i}", "ip": f"10.1.0.{i}", "asset_type": "server"})
    page1 = client.get("/api/audit-logs", headers=h, params={"page": 1, "page_size": 2}).json()["data"]
    assert page1["total"] >= 4
    assert len(page1["items"]) == 2
    page2 = client.get("/api/audit-logs", headers=h, params={"page": 2, "page_size": 2}).json()["data"]
    assert len(page2["items"]) == 2