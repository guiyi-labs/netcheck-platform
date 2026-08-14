"""B1 告警通知分发测试：Webhook / 邮件 / 等级过滤 / 未启用跳过。"""
from __future__ import annotations

import httpx as _httpx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.alert import Alert
from app.services.checkers import CheckResult
from app.services.notifications import dispatch_alert_notifications, LEVEL_RANK

from helpers import wait_run


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_dispatch_disabled_returns_empty(client: TestClient):
    """未启用时不投递。"""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        assert dispatch_alert_notifications(9999, db) == []
    finally:
        db.close()


def test_webhook_called_for_above_level_alerts(client: TestClient, auth_token: str, monkeypatch):
    """达到等级阈值的告警触发 Webhook POST。"""
    # 写入一条 run_id=999、level=warning 的告警（无需实际巡检运行）
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        alert = Alert(
            asset_id=1,
            run_id=999,
            alert_title="测试告警",
            alert_level="warning",
            alert_status="active",
            alert_key="999:test",
            check_type="ping",
            fault_type="测试故障",
            evidence="依据",
            suggestion="建议",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
    finally:
        db.close()

    calls: list[dict] = []

    def fake_post(url, json=None, **kwargs):
        calls.append({"url": url, "json": json})
        return type("Resp", (), {"raise_for_status": lambda self: None})()

    monkeypatch.setattr("app.services.notifications.httpx.post", fake_post)
    monkeypatch.setattr(settings, "notification_enabled", True)
    monkeypatch.setattr(settings, "webhook_url", "http://example.com/hook")
    monkeypatch.setattr(settings, "notification_min_level", "warning")
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "webhook_headers", '{"X-Token":"abc"}')

    db2 = SessionLocal()
    try:
        delivered = dispatch_alert_notifications(999, db2)
    finally:
        db2.close()

    assert len(delivered) == 1 and delivered[0].startswith("webhook:")
    assert len(calls) == 1
    assert calls[0]["url"] == "http://example.com/hook"
    assert calls[0]["json"]["alerts"][0]["id"] == alert_id
    assert calls[0]["json"]["alerts"][0]["level"] == "warning"


def test_email_sent_when_smtp_configured(client: TestClient, auth_token: str, monkeypatch):
    """配置 SMTP 后调用 send_message。"""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        alert = Alert(
            asset_id=1,
            run_id=998,
            alert_title="邮件测试",
            alert_level="major",
            alert_status="active",
            alert_key="998:email",
            check_type="http",
            fault_type="HTTP 异常",
        )
        db.add(alert)
        db.commit()
    finally:
        db.close()

    send_calls: list[tuple[str, str, list[str], str]] = []

    class FakeSMTP_SSL:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def send_message(self, msg):
            send_calls.append((msg["Subject"], msg["From"], [str(msg["To"])], str(msg.get_content())))
        def ehlo(self):
            pass
        def login(self, u, p):
            pass

    monkeypatch.setattr("app.services.notifications.smtplib.SMTP_SSL", FakeSMTP_SSL)
    monkeypatch.setattr(settings, "notification_enabled", True)
    monkeypatch.setattr(settings, "webhook_url", "")
    monkeypatch.setattr(settings, "notification_min_level", "warning")
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.com")
    monkeypatch.setattr(settings, "smtp_from", "net@test.com")
    monkeypatch.setattr(settings, "smtp_to", "admin@test.com")
    monkeypatch.setattr(settings, "smtp_use_ssl", True)
    monkeypatch.setattr(settings, "smtp_user", "net@test.com")
    monkeypatch.setattr(settings, "smtp_password", "secret")

    db3 = SessionLocal()
    try:
        delivered = dispatch_alert_notifications(998, db3)
    finally:
        db3.close()

    assert any(d.startswith("email:") for d in delivered)
    assert len(send_calls) == 1
    assert "邮件测试" in send_calls[0][0] or "邮件测试" in send_calls[0][3]


def test_level_filter_excludes_below(client: TestClient, auth_token: str, monkeypatch):
    """低于阈值的告警不投递。"""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        alert = Alert(
            asset_id=1,
            run_id=997,
            alert_title="次要告警",
            alert_level="minor",
            alert_status="active",
            alert_key="997:minor",
            check_type="ping",
            fault_type="微小异常",
        )
        db.add(alert)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(settings, "notification_enabled", True)
    monkeypatch.setattr(settings, "webhook_url", "http://x.com")
    monkeypatch.setattr(settings, "notification_min_level", "warning")
    monkeypatch.setattr(settings, "smtp_host", "")

    db4 = SessionLocal()
    try:
        delivered = dispatch_alert_notifications(997, db4)
    finally:
        db4.close()

    assert delivered == []