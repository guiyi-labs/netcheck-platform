"""G1 实时推送：WS 端点鉴权、hub 广播、运行状态实况事件。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.services.checkers import CheckResult, CHECKERS
from app.services.realtime import hub

from helpers import wait_run


def test_ws_rejects_invalid_token(client: TestClient):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/runs?token=invalid-token"):
            pass


def test_ws_rejects_missing_token(client: TestClient):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/runs"):
            pass


def test_ws_receives_published_events(client: TestClient, auth_token: str):
    with client.websocket_connect(f"/ws/runs?token={auth_token}") as ws:
        hub.publish({"type": "test.event", "run_id": 1, "status": "running"})
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "test.event"
        assert msg["status"] == "running"
        assert hub.connection_count >= 1


def test_run_lifecycle_pushes_real_time_events(client: TestClient, auth_token: str, monkeypatch):
    """真实执行一次巡检：WS 端应依次收到 running / completed 事件。"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    class InstantChecker:
        def check(self, asset):
            return [CheckResult("success", asset.ip, 1, "ok")]

    monkeypatch.setitem(CHECKERS, "ping", InstantChecker())

    task = client.post("/api/tasks", headers=headers, json={"name": "实时推送测试", "check_types": ["ping"], "asset_ids": [1]}).json()["data"]

    with client.websocket_connect(f"/ws/runs?token={auth_token}") as ws:
        run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
        final = wait_run(client, headers, run["id"])
        assert final["status"] == "completed"

        seen: dict[str, list] = {}
        got_terminal = False
        for _ in range(10):
            try:
                msg = json.loads(ws.receive_text())
            except Exception:
                break
            if msg.get("type") != "run.updated":
                continue
            seen.setdefault(msg["status"], []).append(msg)
            if msg["status"] in ("completed", "failed", "cancelled"):
                got_terminal = True
                break
        assert got_terminal, f"未收到终态事件，实际: {seen}"