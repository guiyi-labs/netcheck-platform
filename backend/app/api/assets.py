from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.asset import Asset
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
    current_user: User = Depends(get_current_user),
) -> Response[AssetOut]:
    asset = Asset(**payload.model_dump())
    db.add(asset)
    db.flush()
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


@router.get("/{asset_id}", response_model=Response[AssetOut])
def get_asset(asset_id: int, db: Session = Depends(get_db)) -> Response[AssetOut]:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    return Response(data=AssetOut.model_validate(asset))


@router.put("/{asset_id}", response_model=Response[AssetOut])
def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response[AssetOut]:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    for field, value in payload.model_dump().items():
        setattr(asset, field, value)
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
    current_user: User = Depends(get_current_user),
) -> Response:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
    detail = f"删除资产 {asset.name} ({asset.ip})"
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
