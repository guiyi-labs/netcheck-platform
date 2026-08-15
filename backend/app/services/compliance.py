"""配置合规基线：将「配置快照 + 行级 diff」组织为轻量合规闭环。

- 基线标记：同一设备最多一个快照标记为 is_baseline=True（作为合规参照）。
- 合规比对：最新快照 vs 基线，生成行级合规报告。
- **粒度如实标注**：规则粒度为配置行级 diff（非语义级；语义级需设备知识，
  不在本模块范围内）。
"""
import logging

from sqlalchemy.orm import Session

from app.models.device import Device, DeviceConfigSnapshot
from app.services.config_backup import diff_configs

logger = logging.getLogger("netcheck.compliance")


def set_baseline(db: Session, device_id: int, snapshot_id: int,
                 enabled: bool = True) -> DeviceConfigSnapshot | None:
    """将某快照标记/取消为设备的合规基线。

    - enabled=False：清除该快照的基线标记。
    - enabled=True：先清掉该设备其他快照的基线标记（保证同设备唯一），
      再把目标快照标记为基线。
    - 返回更新后的快照；设备或快照不存在返回 None。
    """
    device = db.get(Device, device_id)
    if device is None:
        return None
    snapshot = (
        db.query(DeviceConfigSnapshot)
        .filter(DeviceConfigSnapshot.id == snapshot_id,
                DeviceConfigSnapshot.device_id == device_id)
        .first()
    )
    if snapshot is None:
        return None
    if enabled:
        db.query(DeviceConfigSnapshot).filter(
            DeviceConfigSnapshot.device_id == device_id,
            DeviceConfigSnapshot.is_baseline.is_(True),
        ).update({DeviceConfigSnapshot.is_baseline: False})
        snapshot.is_baseline = True
    else:
        snapshot.is_baseline = False
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_compliance_report(db: Session, device_id: int) -> dict | None:
    """生成合规报告：最新快照 vs 基线（行级 diff）。

    返回结构（dict，供 schema 序列化；设备/基线/快照缺失返回 None）：
      {
        "device_id": int,
        "baseline_id": int | None, "baseline_collected_at": datetime | None,
        "current_id": int | None, "current_collected_at": datetime | None,
        "total_rules": int, "passed": int, "failed": int,
        "changed_lines": [{"kind": str, "old_line_no": int|None,
                           "new_line_no": int|None, "text": str}],
        "status": "pass" | "warn" | "fail",
        "status_detail": str,
      }
    """
    device = db.get(Device, device_id)
    if device is None:
        return None

    baseline = (
        db.query(DeviceConfigSnapshot)
        .filter(DeviceConfigSnapshot.device_id == device_id,
                DeviceConfigSnapshot.is_baseline.is_(True))
        .order_by(DeviceConfigSnapshot.collected_at.desc(),
                  DeviceConfigSnapshot.id.desc())
        .first()
    )
    current = (
        db.query(DeviceConfigSnapshot)
        .filter(DeviceConfigSnapshot.device_id == device_id)
        .order_by(DeviceConfigSnapshot.collected_at.desc(),
                  DeviceConfigSnapshot.id.desc())
        .first()
    )
    if baseline is None:
        return {
            "device_id": device_id,
            "baseline_id": None,
            "baseline_collected_at": None,
            "current_id": current.id if current else None,
            "current_collected_at": current.collected_at if current else None,
            "total_rules": 0,
            "passed": 0,
            "failed": 0,
            "changed_lines": [],
            "status": "warn",
            "status_detail": "设备尚未配置合规基线（请先将某快照标记为基线）",
        }
    if current is None:
        return {
            "device_id": device_id,
            "baseline_id": baseline.id,
            "baseline_collected_at": baseline.collected_at,
            "current_id": None,
            "current_collected_at": None,
            "total_rules": 0,
            "passed": 0,
            "failed": 0,
            "changed_lines": [],
            "status": "warn",
            "status_detail": "设备尚无任何配置快照",
        }

    # 行级 diff：变更行即不合规项（粒度如实标注为行级，非语义级）
    lines = diff_configs(
        baseline.config_text_redacted, current.config_text_redacted,
        context_lines=2,
    )
    changed = [ln for ln in lines if ln.get("kind") in ("add", "del")]
    if not changed:
        status, detail = "pass", "当前配置与基线一致，无变更"
    elif len(changed) <= 10:
        status, detail = "warn", f"当前配置与基线存在 {len(changed)} 处行级变更"
    else:
        status, detail = "fail", f"当前配置与基线存在 {len(changed)} 处行级变更（超过阈值）"

    return {
        "device_id": device_id,
        "baseline_id": baseline.id,
        "baseline_collected_at": baseline.collected_at,
        "current_id": current.id,
        "current_collected_at": current.collected_at,
        "total_rules": len(lines),
        "passed": len(lines) - len(changed),
        "failed": len(changed),
        "changed_lines": changed,
        "status": status,
        "status_detail": detail,
    }