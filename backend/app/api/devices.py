"""设备管理 API：设备 CRUD + 凭据登记 + 触发采集 + 采集状态。

安全约定：
- 凭据只用于登记（加密存储），API 只返回是否配置与算法摘要；
- 写操作 require_write；凭据相关操作 require_admin；
- 采集接口触发只读采集，绝不改设备配置。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_write, require_admin
from app.models.device import Device, DeviceCredential, SnmpInterfaceMetric
from app.models.user import User
from app.schemas.common import Response, PageData
from app.schemas.device import (
    DeviceCollectRequest,
    DeviceCollectResponse,
    DeviceCollectStatus,
    DeviceCredentialIn,
    DeviceCredentialOut,
    DeviceIn,
    DeviceListOut,
    DeviceListResponse,
    DeviceOut,
    DeviceResponse,
    SnmpInterfaceOut,
    SnmpInterfaceResponse,
)
from app.services import credential_manager
from app.services.device_collector import collect_device, collect_devices

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _cred_out(cred: DeviceCredential) -> DeviceCredentialOut:
    return DeviceCredentialOut(
        id=cred.id,
        name=cred.name,
        protocol=cred.protocol,
        username=cred.username,
        auth_algorithm=cred.auth_algorithm,
        priv_algorithm=cred.priv_algorithm,
        has_secret=bool(
            cred.auth_key_encrypted or cred.priv_key_encrypted or cred.ssh_key_encrypted
        ),
        external_secret_ref=cred.external_secret_ref or "",
        created_at=cred.created_at,
    )


def _device_out(db: Session, device: Device) -> DeviceOut:
    data = DeviceOut.model_validate(device)
    data.has_snmp = bool(device.snmp_config_id)
    data.has_ssh = bool(device.ssh_config_id)
    return data


# ---- 凭据 ----

@router.post("/credentials", response_model=Response[DeviceCredentialOut],
             status_code=status.HTTP_201_CREATED)
def create_credential(
    payload: DeviceCredentialIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response[DeviceCredentialOut]:
    cred = DeviceCredential(
        name=payload.name,
        protocol=payload.protocol,
        username=payload.username,
        auth_algorithm=payload.auth_algorithm,
        priv_algorithm=payload.priv_algorithm,
        external_secret_ref=payload.external_secret_ref,
    )
    # 加密存储（未配置 NETCHECK_SECRET_KEY 时存空标记，由 collector 报错）
    if payload.auth_key:
        cred.auth_key_encrypted = credential_manager.encrypt_secret(payload.auth_key)
    if payload.priv_key:
        cred.priv_key_encrypted = credential_manager.encrypt_secret(payload.priv_key)
    if payload.ssh_key:
        cred.ssh_key_encrypted = credential_manager.encrypt_secret(payload.ssh_key)
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return Response(data=_cred_out(cred))


@router.get("/credentials", response_model=Response[PageData[DeviceCredentialOut]])
def list_credentials(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response[PageData[DeviceCredentialOut]]:
    query = db.query(DeviceCredential)
    total = query.count()
    items = (
        query.order_by(DeviceCredential.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Response(data=PageData(
        total=total, page=page, page_size=page_size,
        items=[_cred_out(c) for c in items],
    ))


@router.delete("/credentials/{credential_id}", response_model=Response)
def delete_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response:
    cred = db.query(DeviceCredential).filter(DeviceCredential.id == credential_id).first()
    if cred is None:
        raise HTTPException(status_code=404, detail="凭据不存在")
    db.delete(cred)
    db.commit()
    return Response()


# ---- 设备 ----

@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> DeviceResponse:
    device = Device(
        asset_id=payload.asset_id,
        name=payload.name,
        management_ip=payload.management_ip,
        vendor_platform=payload.vendor_platform,
        snmp_config_id=payload.snmp_config_id,
        ssh_config_id=payload.ssh_config_id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return Response(data=_device_out(db, device))


@router.get("", response_model=DeviceListResponse)
def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    vendor: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceListResponse:
    query = db.query(Device)
    if vendor:
        query = query.filter(Device.vendor_platform == vendor)
    total = query.count()
    items = (
        query.order_by(Device.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Response(data=PageData(
        total=total, page=page, page_size=page_size,
        items=[DeviceListOut.model_validate(d) for d in items],
    ))


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceResponse:
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    return Response(data=_device_out(db, device))


@router.get("/{device_id}/interfaces", response_model=SnmpInterfaceResponse)
def list_device_interfaces(
    device_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SnmpInterfaceResponse:
    if db.query(Device).filter(Device.id == device_id).first() is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    metrics = (
        db.query(SnmpInterfaceMetric)
        .filter(SnmpInterfaceMetric.device_id == device_id)
        .order_by(SnmpInterfaceMetric.interface_index.asc(),
                  SnmpInterfaceMetric.collected_at.desc())
        .limit(limit)
        .all()
    )
    return Response(data=[SnmpInterfaceOut.model_validate(m) for m in metrics])


@router.put("/{device_id}", response_model=DeviceResponse)
def update_device(
    device_id: int,
    payload: DeviceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> DeviceResponse:
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    device.name = payload.name
    device.management_ip = payload.management_ip
    device.vendor_platform = payload.vendor_platform
    device.snmp_config_id = payload.snmp_config_id
    device.ssh_config_id = payload.ssh_config_id
    if payload.asset_id is not None:
        device.asset_id = payload.asset_id
    db.commit()
    db.refresh(device)
    return Response(data=_device_out(db, device))


@router.delete("/{device_id}", response_model=Response)
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response:
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    # 清理关联指标
    db.query(SnmpInterfaceMetric).filter(
        SnmpInterfaceMetric.device_id == device_id
    ).delete()
    db.delete(device)
    db.commit()
    return Response()


@router.post("/collect", response_model=DeviceCollectResponse)
def trigger_collect(
    payload: DeviceCollectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> DeviceCollectResponse:
    """触发指定设备采集（最多 8 台，同步执行）。"""
    results = collect_devices(db, payload.device_ids)
    first = results[0] if results else {"status": "error", "error": "无设备"}
    return Response(data=DeviceCollectStatus.model_validate(first))


@router.post("/{device_id}/collect", response_model=DeviceCollectResponse)
def trigger_collect_one(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> DeviceCollectResponse:
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    result = collect_device(db, device)
    return Response(data=DeviceCollectStatus.model_validate(result))