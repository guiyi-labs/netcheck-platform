"""D1 AI 辅助诊断：端点鉴权、未启用回落、正常增强。"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services.checkers import CheckResult, CHECKERS

from helpers import wait_run


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _setup_run(client: TestClient, auth_token: str, monkeypatch) -> int:
    """创建任务并执行，返回 diagnosis_id（至少产生一条 failed 检查结果）。"""
    headers = _h(auth_token)
    class FailChecker:
        def check(self, asset):
            return [CheckResult("failed", asset.ip, 10, error_message="ping 失败")]
    monkeypatch.setitem(CHECKERS, "ping", FailChecker())
    task = client.post("/api/tasks", headers=headers, json={"name": "AI测试任务", "check_types": ["ping"], "asset_ids": [1]}).json()["data"]
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    wait_run(client, headers, run["id"])
    diags = client.get(f"/api/diagnosis/runs/{run['id']}", headers=headers).json()["data"]
    assert diags["items"], "没有诊断记录"
    return diags["items"][0]["id"]


def test_ai_endpoint_returns_409_when_disabled(client: TestClient, auth_token: str, monkeypatch):
    diagnosis_id = _setup_run(client, auth_token, monkeypatch)
    resp = client.post(f"/api/diagnosis/{diagnosis_id}/ai-suggestion", headers=_h(auth_token))
    assert resp.status_code == 409
    assert "未启用" in resp.json()["detail"]


def test_ai_endpoint_returns_error_when_service_fails(client: TestClient, auth_token: str, monkeypatch):
    diagnosis_id = _setup_run(client, auth_token, monkeypatch)
    from app.core.config import settings
    monkeypatch.setattr(settings, "ai_diagnosis_enabled", True)
    monkeypatch.setattr(settings, "ai_base_url", "http://127.0.0.1:9999")
    monkeypatch.setattr(settings, "ai_api_key", "sk-test")

    def boom(*a, **k):
        raise ConnectionError("refused")

    monkeypatch.setattr("app.services.ai_diagnosis.httpx.post", boom)
    resp = client.post(f"/api/diagnosis/{diagnosis_id}/ai-suggestion", headers=_h(auth_token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "error"
    assert "refused" in data["message"]


def test_ai_endpoint_returns_enhanced_suggestion(client: TestClient, auth_token: str, monkeypatch):
    diagnosis_id = _setup_run(client, auth_token, monkeypatch)
    from app.core.config import settings
    monkeypatch.setattr(settings, "ai_diagnosis_enabled", True)
    monkeypatch.setattr(settings, "ai_base_url", "http://mock-llm")
    monkeypatch.setattr(settings, "ai_api_key", "sk-test")
    monkeypatch.setattr(settings, "ai_model", "test-model")

    def fake_post(url, json=None, **kwargs):
        choice = {"message": {"content": "建议优先检查防火墙入站规则与 ARP 缓存。"}}
        return SimpleNamespace(json=lambda: {"choices": [choice], "model": "test-model"}, raise_for_status=lambda: None)

    monkeypatch.setattr("app.services.ai_diagnosis.httpx.post", fake_post)
    resp = client.post(f"/api/diagnosis/{diagnosis_id}/ai-suggestion", headers=_h(auth_token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "ok"
    assert "防火墙" in data["content"]
    assert data["model"] == "test-model"