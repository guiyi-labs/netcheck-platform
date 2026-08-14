"""G2 趋势统计 API：RTT 曲线 / 可用率 / 运行耗时。"""
from fastapi.testclient import TestClient

from app.services.checkers import CheckResult, CHECKERS

from helpers import wait_run


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _run_task(client: TestClient, auth_token: str, name: str = "统计测试") -> int:
    headers = _h(auth_token)
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": name, "check_types": ["ping"], "asset_ids": [1]},
    ).json()["data"]
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    wait_run(client, headers, run["id"])
    return task["id"]


def test_stats_requires_auth(client: TestClient):
    assert client.get("/api/stats/assets").status_code == 401


def test_stats_assets_lists_assets(client: TestClient, auth_token: str):
    data = client.get("/api/stats/assets", headers=_h(auth_token)).json()["data"]
    assert len(data) >= 12
    assert all("id" in item and "name" in item for item in data)


def test_rtt_trend_after_run(client: TestClient, auth_token: str, monkeypatch):
    class FixedChecker:
        def check(self, asset):
            return [CheckResult("success", asset.ip, 42.0, "ok")]

    monkeypatch.setitem(CHECKERS, "ping", FixedChecker())
    _run_task(client, auth_token)
    data = client.get("/api/stats/rtt-trend?asset_id=1&days=7", headers=_h(auth_token)).json()["data"]
    assert len(data) == 7
    today = data[-1]
    assert today["avg_response_ms"] == 42.0
    assert today["max_response_ms"] == 42.0


def test_availability_after_run(client: TestClient, auth_token: str, monkeypatch):
    class OkChecker:
        def check(self, asset):
            return [CheckResult("success", asset.ip, 1, "ok")]

    monkeypatch.setitem(CHECKERS, "ping", OkChecker())
    _run_task(client, auth_token)
    data = client.get("/api/stats/availability?asset_id=1&days=7", headers=_h(auth_token)).json()["data"]
    assert len(data) == 7
    today = data[-1]
    assert today["total"] >= 1
    assert today["rate"] == 100.0


def test_run_durations_after_run(client: TestClient, auth_token: str, monkeypatch):
    class SlowChecker:
        def check(self, asset):
            import time

            time.sleep(0.05)
            return [CheckResult("success", asset.ip, 5, "ok")]

    monkeypatch.setitem(CHECKERS, "ping", SlowChecker())
    _run_task(client, auth_token)
    data = client.get("/api/stats/run-durations?days=7", headers=_h(auth_token)).json()["data"]
    assert len(data) >= 1
    assert data[-1]["duration_s"] is not None
    assert data[-1]["status"] == "completed"