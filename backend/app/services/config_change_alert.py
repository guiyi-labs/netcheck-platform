"""N4 配置变化事件与告警：独立于巡检 run 的事实表 → Alert 联动。

- collect_config_snapshot 检测到 changed=True 时，由本模块登记 ConfigChangeEvent；
- 同一 diff_hash（同一次配置变化）只触发一次告警，直到配置再次变化
  （alert_key = device:{id}:config_change:{diff_hash} 去重）；
- 设备→资产映射缺失时不产生孤儿 Alert，事件标记 resolved=False + note；
- 通知失败不重复创建同一 Alert（幂等由事件唯一约束保证）。
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.asset import Asset
from app.models.device import ConfigChangeEvent, Device, DeviceConfigSnapshot

logger = logging.getLogger("netcheck.config_event")

CONFIG_CHANGE_FAULT_TYPE = "config_change"


def _device_asset_key(db: Session, device: Device) -> str | None:
    """设备管理地址对应的资产（用于 Alert.asset_id 关联）。无匹配返回 None。"""
    assets = (
        db.query(Asset)
        .filter(Asset.ip == device.management_ip)
        .order_by(Asset.id.desc())
        .limit(5)
        .all()
    )
    return assets[0] if assets else None


def record_config_change_event(db: Session, device: Device,
                               snapshot: DeviceConfigSnapshot,
                               diff_text: str | None = None) -> dict:
    """登记配置变化事件并联动告警。返回事件状态（无真实凭据）。"""
    from app.services.config_backup import diff_configs, format_diff_text

    # diff_hash = 新快照内容哈希（同一次变化唯一）
    diff_hash = snapshot.config_full_hash

    # 幂等：同一快照已登记过则不重复
    existing_event = (
        db.query(ConfigChangeEvent)
        .filter(
            ConfigChangeEvent.device_id == device.id,
            ConfigChangeEvent.snapshot_id == snapshot.id,
        )
        .first()
    )
    if existing_event is not None:
        return {"status": "already_recorded", "event_id": existing_event.id}

    # 变化行数（与前一份快照 diff）
    changed_lines = 0
    if diff_text is None:
        prev = (
            db.query(DeviceConfigSnapshot)
            .filter(
                DeviceConfigSnapshot.device_id == device.id,
                DeviceConfigSnapshot.id != snapshot.id,
            )
            .order_by(DeviceConfigSnapshot.collected_at.desc(),
                      DeviceConfigSnapshot.id.desc())
            .first()
        )
        if prev is not None:
            try:
                rows = diff_configs(prev.config_text_redacted, snapshot.config_text_redacted)
                changed_lines = len([r for r in rows if r["kind"] in ("add", "del")])
            except Exception:  # noqa: BLE001
                changed_lines = 0

    asset = _device_asset_key(db, device)
    event = ConfigChangeEvent(
        device_id=device.id,
        snapshot_id=snapshot.id,
        diff_hash=diff_hash,
        alert_key=f"device:{device.id}:config_change:{diff_hash}",
        changed_lines=changed_lines,
        resolved=False,
        note=None if asset is not None else "设备未关联资产，跳过告警",
    )
    db.add(event)
    db.flush()

    alert_id = None
    if asset is not None:
        alert = _upsert_config_change_alert(db, device, asset, event, changed_lines)
        if alert is not None:
            alert_id = alert.id
            event.alert_id = alert_id
            event.resolved = True
    db.commit()
    return {
        "status": "recorded",
        "event_id": event.id,
        "alert_id": alert_id,
        "changed_lines": changed_lines,
        "note": event.note,
    }


def _upsert_config_change_alert(db: Session, device: Device, asset,
                                event: ConfigChangeEvent,
                                changed_lines: int) -> Alert | None:
    """按 alert_key 幂等创建/更新配置变化 Alert（复用告警通道）。"""
    now = datetime.now()
    existing = (
        db.query(Alert)
        .filter(
            Alert.alert_key == event.alert_key,
            Alert.alert_status != "recovered",
        )
        .order_by(Alert.id.desc())
        .first()
    )
    evidence = (
        f"设备配置发生变化（{changed_lines} 行变更）。设备：{device.name or device.management_ip}，"
        f"快照 #{event.snapshot_id}，diff {event.diff_hash[:12]}…"
    )
    suggestion = "登录设备核对变更内容；如需回滚请联系管理员并参考配置备份历史。"
    if existing is not None:
        existing.alert_title = "设备配置变更"
        existing.alert_level = "warning"
        existing.evidence = evidence
        existing.suggestion = suggestion
        existing.last_triggered_at = now
        existing.trigger_count += 1
        return existing

    alert = Alert(
        asset_id=asset.id,
        run_id=0,  # 独立于巡检 run
        result_id=None,
        diagnosis_id=None,
        alert_title="设备配置变更",
        alert_level="warning",
        alert_status="active",
        alert_key=event.alert_key,
        check_type="config_backup",
        fault_type=CONFIG_CHANGE_FAULT_TYPE,
        evidence=evidence,
        suggestion=suggestion,
        first_triggered_at=now,
        last_triggered_at=now,
        trigger_count=1,
        consecutive_failures=1,
        consecutive_successes=0,
    )
    db.add(alert)
    db.flush()
    return alert