"""资产变更日志服务：对比字段差异并落库，供 /api/assets/{id}/changes 查询。"""
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetChangeLog

# 参与变更对比的业务字段
TRACKED_FIELDS = [
    "name",
    "ip",
    "hostname",
    "asset_type",
    "location",
    "os_type",
    "business_name",
    "ports",
    "owner",
    "status",
    "remark",
]

FIELD_LABELS = {
    "name": "名称",
    "ip": "IP",
    "hostname": "主机名",
    "asset_type": "资产类型",
    "location": "区域",
    "os_type": "操作系统",
    "business_name": "业务系统",
    "ports": "端口",
    "owner": "负责人",
    "status": "状态",
    "remark": "备注",
}


def snapshot_asset(asset: Asset) -> dict:
    return {field: getattr(asset, field) for field in TRACKED_FIELDS}


def record_asset_create(db: Session, asset: Asset, username: str) -> None:
    snapshot = snapshot_asset(asset)
    changed = {field: value for field, value in snapshot.items() if value not in (None, "")}
    db.add(
        AssetChangeLog(
            asset_id=asset.id,
            action="create",
            field=",".join(changed.keys()) or "*",
            old_value=None,
            new_value="\n".join(f"{FIELD_LABELS.get(k, k)}={v}" for k, v in changed.items()),
            username=username,
            detail=f"新增资产 {asset.name or asset.ip}",
        )
    )


def record_asset_update(db: Session, asset_id: int, before: dict, after: dict, username: str) -> None:
    for field, new_value in after.items():
        old_value = before.get(field)
        if old_value != new_value:
            db.add(
                AssetChangeLog(
                    asset_id=asset_id,
                    action="update",
                    field=field,
                    old_value="-" if old_value in (None, "") else str(old_value),
                    new_value="-" if new_value in (None, "") else str(new_value),
                    username=username,
                    detail=f"更新 {FIELD_LABELS.get(field, field)}",
                )
            )


def record_asset_delete(db: Session, asset: Asset, username: str) -> None:
    snapshot = snapshot_asset(asset)
    body = "\n".join(f"{FIELD_LABELS.get(k, k)}={v}" for k, v in snapshot.items() if v not in (None, ""))
    db.add(
        AssetChangeLog(
            asset_id=asset.id,
            action="delete",
            field="*",
            old_value=body,
            new_value=None,
            username=username,
            detail=f"删除资产 {asset.name or asset.ip}",
        )
    )