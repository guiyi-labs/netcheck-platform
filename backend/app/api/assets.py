import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_write
from app.models.asset import Asset, AssetChangeLog
from app.models.user import User
from app.schemas.asset import (
    ASSET_STATUSES,
    ASSET_TYPES,
    AssetCreate,
    AssetMeta,
    AssetOut,
    AssetUpdate,
)
from app.schemas.common import PageData, Response
from app.services import audit
from app.services.asset_change import record_asset_create, record_asset_update, record_asset_delete, snapshot_asset

router = APIRouter(
    prefix="/api/assets",
    tags=["assets"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=Response[PageData[AssetOut]])
def list_assets(
    name: str | None = None,
    ip: str | None = None,
    asset_type: str | None = None,
    location: str | None = None,
    status_: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Response[PageData[AssetOut]]:
    q = db.query(Asset)
    if name:
        q = q.filter(Asset.name.contains(name))
    if ip:
        q = q.filter(Asset.ip.contains(ip))
    if asset_type:
        q = q.filter(Asset.asset_type == asset_type)
    if location:
        q = q.filter(Asset.location == location)
    if status_:
        q = q.filter(Asset.status == status_)

    total = q.count()
    items = (
        q.order_by(Asset.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Response(
        data=PageData(
            total=total,
            page=page,
            page_size=page_size,
            items=[AssetOut.model_validate(a) for a in items],
        )
    )


@router.get("/meta/types", response_model=Response[AssetMeta])
def asset_types(db: Session = Depends(get_db)) -> Response[AssetMeta]:
    """下拉选项元数据，供前端筛选与表单使用。"""
    locations = [
        row[0] for row in db.query(Asset.location).filter(Asset.location.isnot(None)).distinct().all()
    ]
    return Response(
        data=AssetMeta(
            asset_types=ASSET_TYPES,
            statuses=ASSET_STATUSES,
        )
    )


@router.post("", response_model=Response[AssetOut], status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response[AssetOut]:
    asset = Asset(**payload.model_dump())
    db.add(asset)
    db.flush()
    record_asset_create(db, asset, current_user.username)
    audit.record(
        db,
        current_user.username,
        "asset.create",
        target_type="asset",
        target_id=asset.id,
        detail=f"新增资产 {asset.name} ({asset.ip})",
        request=request,
    )
    db.commit()
    db.refresh(asset)
    return Response(data=AssetOut.model_validate(asset))


@router.post("/import", response_model=Response[dict])
def import_assets(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response[dict]:
    """批量导入资产 CSV：name,ip,hostname,asset_type,location,os_type,business_name,ports,owner,status,remark"""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="请上传 CSV 文件")
    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="CSV 必须使用 UTF-8 编码")

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    required = {"name", "ip"}
    if not required.issubset(fieldnames):
        raise HTTPException(status_code=422, detail=f"CSV 缺少必需字段 name/ip，实际字段：{','.join(fieldnames)}")

    imported = 0
    skipped = 0
    errors: list[dict] = []
    for row_number, row in enumerate(reader, start=2):
        name = (row.get("name") or "").strip()
        ip = (row.get("ip") or "").strip()
        if not name or not ip:
            skipped += 1
            errors.append({"row": row_number, "error": "name/ip 不能为空"})
            continue
        if db.query(Asset).filter(Asset.ip == ip).first() is not None:
            skipped += 1
            errors.append({"row": row_number, "error": f"IP {ip} 已存在"})
            continue
        asset_type = (row.get("asset_type") or "server").strip()
        if asset_type not in ASSET_TYPES:
            asset_type = "server"
        status_value = (row.get("status") or "unknown").strip()
        if status_value not in ASSET_STATUSES:
            status_value = "unknown"
        asset = Asset(
            name=name,
            ip=ip,
            hostname=(row.get("hostname") or "").strip() or None,
            asset_type=asset_type,
            location=(row.get("location") or "").strip() or None,
            os_type=(row.get("os_type") or "").strip() or None,
            business_name=(row.get("business_name") or "").strip() or None,
            ports=(row.get("ports") or "").strip() or None,
            owner=(row.get("owner") or "").strip() or None,
            status=status_value,
            remark=(row.get("remark") or "").strip() or None,
        )
        db.add(asset)
        db.flush()
        imported += 1

    audit.record(
        db,
        current_user.username,
        "asset.import",
        target_type="asset",
        detail=f"批量导入资产：成功 {imported} 条，跳过 {skipped} 条",
        request=request,
    )
    db.commit()
    return Response(
        message=f"导入完成：成功 {imported} 条，跳过 {skipped} 条",
        data={"imported": imported, "skipped": skipped, "errors": errors},
    )


@router.get("/export", response_model=None)
def export_assets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> FastAPIResponse:
    """导出全部资产为 CSV（UTF-8 with BOM，Excel 可直接打开）。"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "ip", "hostname", "asset_type", "location", "os_type", "business_name", "ports", "owner", "status", "remark"])
    for asset in db.query(Asset).order_by(Asset.id).all():
        writer.writerow([
            asset.name,
            asset.ip,
            asset.hostname or "",
            asset.asset_type,
            asset.location or "",
            asset.os_type or "",
            asset.business_name or "",
            asset.ports or "",
            asset.owner or "",
            asset.status,
            asset.remark or "",
        ])
    content = "\ufeff" + output.getvalue()
    return FastAPIResponse(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=assets.csv"},
    )


@router.get("/{asset_id}", response_model=Response[AssetOut])
def get_asset(asset_id: int, db: Session = Depends(get_db)) -> Response[AssetOut]:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    return Response(data=AssetOut.model_validate(asset))


@router.get("/{asset_id}/changes", response_model=Response[PageData[dict]])
def list_asset_changes(
    asset_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Response[PageData[dict]]:
    """资产变更历史：新增/更新（字段级 diff）/删除记录。"""
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    query = db.query(AssetChangeLog).filter(AssetChangeLog.asset_id == asset_id)
    total = query.count()
    items = (
        query.order_by(AssetChangeLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Response(
        data=PageData(
            total=total,
            page=page,
            page_size=page_size,
            items=[
                {
                    "id": item.id,
                    "asset_id": item.asset_id,
                    "action": item.action,
                    "field": item.field,
                    "old_value": item.old_value,
                    "new_value": item.new_value,
                    "username": item.username,
                    "detail": item.detail,
                    "changed_at": item.changed_at,
                }
                for item in items
            ],
        )
    )


@router.put("/{asset_id}", response_model=Response[AssetOut])
def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response[AssetOut]:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    before = snapshot_asset(asset)
    for field, value in payload.model_dump().items():
        setattr(asset, field, value)
    after = snapshot_asset(asset)
    record_asset_update(db, asset.id, before, after, current_user.username)
    audit.record(
        db,
        current_user.username,
        "asset.update",
        target_type="asset",
        target_id=asset_id,
        detail=f"更新资产 {asset.name} ({asset.ip})",
        request=request,
    )
    db.commit()
    db.refresh(asset)
    return Response(data=AssetOut.model_validate(asset))


@router.delete("/{asset_id}", response_model=Response)
def delete_asset(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    detail = f"删除资产 {asset.name} ({asset.ip})"
    record_asset_delete(db, asset, current_user.username)
    db.delete(asset)
    audit.record(
        db,
        current_user.username,
        "asset.delete",
        target_type="asset",
        target_id=asset_id,
        detail=detail,
        request=request,
    )
    db.commit()
    return Response(message="已删除")
