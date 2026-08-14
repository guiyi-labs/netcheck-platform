from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_write
from app.models.discovery import DiscoveryResult, DiscoveryScan
from app.models.user import User
from app.schemas.asset import AssetOut
from app.schemas.common import PageData, Response
from app.schemas.discovery import DiscoveryResultOut, DiscoveryScanCreate, DiscoveryScanOut
from app.services import audit
from app.services.discovery import import_discovery_result, run_discovery_scan

router = APIRouter(
    prefix="/api/discovery",
    tags=["discovery"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/scans", response_model=Response[DiscoveryScanOut], status_code=status.HTTP_201_CREATED)
def create_scan(
    payload: DiscoveryScanCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response[DiscoveryScanOut]:
    scan = run_discovery_scan(payload, db)
    audit.record(
        db,
        current_user.username,
        "discovery.scan",
        target_type="discovery_scan",
        target_id=scan.id,
        detail=f"发起资产发现扫描 {payload.target_range}",
        request=request,
    )
    db.commit()
    db.refresh(scan)
    return Response(data=DiscoveryScanOut.model_validate(scan))


@router.get("/scans", response_model=Response[PageData[DiscoveryScanOut]])
def list_scans(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> Response[PageData[DiscoveryScanOut]]:
    q = db.query(DiscoveryScan)
    total = q.count()
    items = q.order_by(DiscoveryScan.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[DiscoveryScanOut.model_validate(item) for item in items]))


@router.get("/scans/{scan_id}/results", response_model=Response[PageData[DiscoveryResultOut]])
def list_scan_results(scan_id: int, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200), db: Session = Depends(get_db)) -> Response[PageData[DiscoveryResultOut]]:
    q = db.query(DiscoveryResult).filter(DiscoveryResult.scan_id == scan_id)
    total = q.count()
    items = q.order_by(DiscoveryResult.id).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[DiscoveryResultOut.model_validate(item) for item in items]))


@router.post("/results/{result_id}/import", response_model=Response[AssetOut])
def import_result(
    result_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response[AssetOut]:
    asset = import_discovery_result(result_id, db)
    audit.record(
        db,
        current_user.username,
        "discovery.import",
        target_type="asset",
        target_id=asset.id,
        detail=f"从发现结果导入资产 {asset.name} ({asset.ip})",
        request=request,
    )
    db.commit()
    db.refresh(asset)
    return Response(data=AssetOut.model_validate(asset))
