"""告警通知分发：邮件（SMTP）与 Webhook。

- `dispatch_alert_notifications(run_id, db)` 在巡检运行完成后被执行器调用；
  只有 `NETCHECK_NOTIFICATION_ENABLED=true` 且存在达到等级阈值的告警时才会投递。
- 未配置对应渠道（smtp_host / webhook_url）时自动跳过，任何投递异常只记录日志，
  不影响巡检主流程。
"""
import json
import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.core.config import settings
from app.models.alert import Alert

logger = logging.getLogger("netcheck.notifications")

# 告警等级排序（高级别覆盖低级别）
LEVEL_RANK = {"minor": 1, "warning": 2, "major": 3, "critical": 4}


def _enabled() -> bool:
    return bool(settings.notification_enabled)


def _meets_level(level: str) -> bool:
    if not settings.notification_min_level:
        return True
    return LEVEL_RANK.get(level, 0) >= LEVEL_RANK.get(settings.notification_min_level, 0)


def _webhook_headers() -> dict[str, str]:
    raw = (settings.webhook_headers or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(key): str(value) for key, value in parsed.items()}
    except ValueError:
        pass
    headers: dict[str, str] = {}
    for line in raw.replace(";", "\n").splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()
    return headers


def _to_payload(alerts: list[Alert]) -> dict:
    return {
        "source": "netcheck-platform",
        "alerts": [
            {
                "id": alert.id,
                "title": alert.alert_title,
                "level": alert.alert_level,
                "status": alert.alert_status,
                "asset_id": alert.asset_id,
                "check_type": alert.check_type,
                "fault_type": alert.fault_type,
                "evidence": alert.evidence,
                "suggestion": alert.suggestion,
                "trigger_count": alert.trigger_count,
                "first_triggered_at": alert.first_triggered_at.isoformat() if alert.first_triggered_at else None,
            }
            for alert in alerts
        ],
    }


# ---- Webhook 平台适配器（generic / dingtalk / wecom / feishu）----

WEBHOOK_SCHEMES = {"generic", "dingtalk", "wecom", "feishu"}


def _alert_lines(alerts: list[Alert]) -> list[str]:
    lines = [f"巡检诊断平台告警通知（{len(alerts)} 条）", "=" * 40]
    for alert in alerts:
        lines.append(f"- [{alert.alert_level}] {alert.alert_title}")
        lines.append(f"  资产: #{alert.asset_id}  检测: {alert.check_type}  故障: {alert.fault_type}")
        if alert.evidence:
            lines.append(f"  依据: {alert.evidence}")
        if alert.suggestion:
            lines.append(f"  建议: {alert.suggestion}")
        lines.append("")
    return lines


def _build_platform_payload(alerts: list[Alert]) -> dict:
    """按 webhook_scheme 构造对应平台的机器人消息体。"""
    scheme = (settings.webhook_scheme or "generic").lower()
    content = "\n".join(_alert_lines(alerts))
    if scheme == "dingtalk":
        return {
            "msgtype": "markdown",
            "markdown": {"title": f"[netcheck] {len(alerts)} 条告警", "text": content},
        }
    if scheme == "wecom":
        return {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
    if scheme == "feishu":
        return {
            "msg_type": "text",
            "content": {"text": content},
        }
    return _to_payload(alerts)


def _send_webhook(alerts: list[Alert]) -> int:
    if not settings.webhook_url:
        return 0
    resp = httpx.post(
        settings.webhook_url,
        json=_build_platform_payload(alerts),
        headers=_webhook_headers(),
        timeout=10.0,
    )
    resp.raise_for_status()
    return len(alerts)


def _send_email(alerts: list[Alert]) -> int:
    if not settings.smtp_host or not settings.smtp_from or not settings.smtp_to:
        return 0
    lines = [f"巡检诊断平台告警通知（{len(alerts)} 条）", "=" * 40]
    for alert in alerts:
        lines.append(f"- [{alert.alert_level}] {alert.alert_title}")
        lines.append(f"  资产: #{alert.asset_id}  检测: {alert.check_type}  故障: {alert.fault_type}")
        if alert.evidence:
            lines.append(f"  依据: {alert.evidence}")
        if alert.suggestion:
            lines.append(f"  建议: {alert.suggestion}")
        lines.append("")
    message = EmailMessage()
    message["Subject"] = f"[netcheck] {len(alerts)} 条告警通知"
    message["From"] = settings.smtp_from
    message["To"] = settings.smtp_to
    message.set_content("\n".join(lines))

    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=10) as server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.ehlo()
            try:
                server.starttls(context=context)
                server.ehlo()
            except Exception:
                logger.warning("SMTP STARTTLS 不可用，改用明文发送")
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    return len(alerts)


def dispatch_alert_notifications(run_id: int, db) -> list[str]:
    """分发一次巡检运行产生的告警通知，返回投递渠道摘要；未启用/无告警/不足阈值时为空列表。"""
    if not _enabled():
        return []
    alerts = (
        db.query(Alert)
        .filter(Alert.run_id == run_id)
        .order_by(Alert.id)
        .all()
    )
    selected = [alert for alert in alerts if _meets_level(alert.alert_level)]
    if not selected:
        return []
    delivered: list[str] = []
    if settings.webhook_url:
        try:
            count = _send_webhook(selected)
            if count:
                delivered.append(f"webhook:{count}")
        except Exception as exc:
            logger.exception("Webhook 通知失败")
            delivered.append(f"webhook:error:{exc}")
    if settings.smtp_host:
        try:
            count = _send_email(selected)
            if count:
                delivered.append(f"email:{count}")
        except Exception as exc:
            logger.exception("邮件通知失败")
            delivered.append(f"email:error:{exc}")
    if delivered:
        logger.info("运行 %s 告警通知投递：%s", run_id, ",".join(delivered))
    return delivered