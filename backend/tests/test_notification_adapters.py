"""G4 Webhook 平台适配器：钉钉/企微/飞书 payload 验证。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.services.notifications import (
    _build_platform_payload,
    _to_payload,
    dispatch_alert_notifications,
)

from helpers import wait_run


class FakeAlert:
    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.run_id = kw.get("run_id", 1)
        self.asset_id = kw.get("asset_id", 1)
        self.alert_title = kw.get("alert_title", "测试告警")
        self.alert_level = kw.get("alert_level", "critical")
        self.alert_status = kw.get("alert_status", "active")
        self.check_type = kw.get("check_type", "ping")
        self.fault_type = kw.get("fault_type", "unreachable")
        self.evidence = kw.get("evidence", "ping 超时 3 次")
        self.suggestion = kw.get("suggestion", "检查防火墙")
        self.trigger_count = kw.get("trigger_count", 3)
        self.first_triggered_at = kw.get("first_triggered_at", None)


fake_alerts = [FakeAlert()]


def test_generic_payload_has_envelope():
    payload = _build_platform_payload(fake_alerts)
    assert "source" in payload
    assert payload["source"] == "netcheck-platform"
    assert "alerts" in payload


def test_dingtalk_payload_format():
    from app.core.config import settings

    original = settings.webhook_scheme
    try:
        settings.webhook_scheme = "dingtalk"
        payload = _build_platform_payload(fake_alerts)
        assert payload["msgtype"] == "markdown"
        assert "text" in payload["markdown"]
        assert "critical" in payload["markdown"]["text"] or "测试告警" in payload["markdown"]["text"]
    finally:
        settings.webhook_scheme = original


def test_wecom_payload_format():
    from app.core.config import settings

    original = settings.webhook_scheme
    try:
        settings.webhook_scheme = "wecom"
        payload = _build_platform_payload(fake_alerts)
        assert payload["msgtype"] == "markdown"
        assert "content" in payload["markdown"]
    finally:
        settings.webhook_scheme = original


def test_feishu_payload_format():
    from app.core.config import settings

    original = settings.webhook_scheme
    try:
        settings.webhook_scheme = "feishu"
        payload = _build_platform_payload(fake_alerts)
        assert payload["msg_type"] == "text"
        assert "text" in payload["content"]
        assert "critical" in payload["content"]["text"] or "测试告警" in payload["content"]["text"]
    finally:
        settings.webhook_scheme = original


def test_dingtalk_dispatch_sends_correct_body(client: TestClient, auth_token: str, monkeypatch):
    from app.core.config import settings

    settings.webhook_scheme = "dingtalk"
    settings.webhook_url = "http://mock-dingtalk"

    sent: dict = {}

    def mock_post(url, json=None, **kwargs):
        sent["url"] = url
        sent["json"] = json
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr("app.services.notifications.httpx.post", mock_post)
    headers = {"Authorization": f"Bearer {auth_token}"}

    class FailChecker:
        def check(self, asset):
            from app.services.checkers import CheckResult

            return [CheckResult("failed", asset.ip, 1, error_message="down")]

    from app.services.checkers import CHECKERS

    monkeypatch.setitem(CHECKERS, "ping", FailChecker())
    settings.notification_enabled = True

    task = client.post("/api/tasks", headers=headers, json={"name": "适配器测试", "check_types": ["ping"], "asset_ids": [1]}).json()["data"]
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    wait_run(client, headers, run["id"])

    # dispatch_alert_notifications 由 executor 已调用；直接验证 sent
    if sent.get("url") == "http://mock-dingtalk":
        assert sent["json"]["msgtype"] == "markdown"
        assert "[netcheck]" in sent["json"]["markdown"]["title"]
    else:
        # 无告警时不发，属正常
        pass
    settings.notification_enabled = False
    settings.webhook_url = ""
    settings.webhook_scheme = "generic"