import ipaddress
import socket
import subprocess
import platform
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asset import Asset
from app.models.discovery import DiscoveryResult, DiscoveryScan
from app.schemas.discovery import DiscoveryScanCreate

SCAN_MODES = {"ping", "port", "ping_port"}
MAX_TARGETS = 256


def parse_targets(target_range: str) -> list[str]:
    targets: list[str] = []
    try:
        for part in [item.strip() for item in target_range.split(",") if item.strip()]:
            if "/" in part:
                network = ipaddress.ip_network(part, strict=False)
                targets.extend(str(ip) for ip in network.hosts())
            else:
                targets.append(str(ipaddress.ip_address(part)))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="目标范围格式不合法") from exc
    targets = list(dict.fromkeys(targets))
    if not targets:
        raise HTTPException(status_code=422, detail="目标范围不能为空")
    if len(targets) > MAX_TARGETS:
        raise HTTPException(status_code=422, detail="单次发现最多支持256个目标")
    return targets


def parse_ports(ports: str | None) -> list[int]:
    values = []
    for item in (ports or "").split(","):
        item = item.strip()
        if item.isdigit() and 1 <= int(item) <= 65535:
            values.append(int(item))
    return list(dict.fromkeys(values))


def ping_probe(ip: str) -> bool:
    command = ["ping", "-n" if platform.system() == "Windows" else "-c", "1", ip]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=settings.ping_timeout, check=False).returncode == 0
    except Exception:
        return False


def port_probe(ip: str, ports: list[int]) -> list[int]:
    opened = []
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=min(settings.tcp_timeout, 1.0)):
                opened.append(port)
        except Exception:
            continue
    return opened


def reverse_hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def run_discovery_scan(payload: DiscoveryScanCreate, db: Session) -> DiscoveryScan:
    if payload.scan_mode not in SCAN_MODES:
        raise HTTPException(status_code=422, detail="不支持的发现模式")
    targets = parse_targets(payload.target_range)
    ports = parse_ports(payload.ports)
    if payload.scan_mode in {"port", "ping_port"} and not ports:
        raise HTTPException(status_code=422, detail="端口模式必须提供合法端口")

    scan = DiscoveryScan(target_range=payload.target_range, scan_mode=payload.scan_mode, ports=payload.ports, status="running", total_targets=len(targets))
    db.add(scan)
    db.commit()
    db.refresh(scan)

    discovered_count = 0
    try:
        for ip in targets:
            alive = ping_probe(ip) if payload.scan_mode in {"ping", "ping_port"} else False
            open_ports = port_probe(ip, ports) if payload.scan_mode in {"port", "ping_port"} else []
            discovered = alive or bool(open_ports)
            if not discovered:
                continue
            asset = db.query(Asset).filter(Asset.ip == ip).first()
            result = DiscoveryResult(
                scan_id=scan.id,
                ip=ip,
                hostname=reverse_hostname(ip),
                open_ports=",".join(str(port) for port in open_ports) if open_ports else None,
                status="online" if discovered else "unknown",
                already_exists=asset is not None,
                matched_asset_id=asset.id if asset else None,
            )
            db.add(result)
            discovered_count += 1
        scan.status = "completed"
    except Exception as exc:
        scan.status = "failed"
        scan.error_message = str(exc)
    scan.discovered_count = discovered_count
    scan.finished_at = datetime.now()
    db.commit()
    db.refresh(scan)
    return scan


def import_discovery_result(result_id: int, db: Session) -> Asset:
    result = db.get(DiscoveryResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="发现结果不存在")
    existing = db.query(Asset).filter(Asset.ip == result.ip).first()
    if existing is not None:
        result.already_exists = True
        result.matched_asset_id = existing.id
        result.imported_asset_id = existing.id
        db.commit()
        db.refresh(existing)
        return existing
    asset = Asset(
        name=result.hostname or f"发现资产-{result.ip}",
        ip=result.ip,
        hostname=result.hostname,
        asset_type="server",
        ports=result.open_ports,
        status=result.status or "unknown",
        remark="资产发现导入",
    )
    db.add(asset)
    db.flush()
    result.imported_asset_id = asset.id
    result.matched_asset_id = asset.id
    result.already_exists = True
    db.commit()
    db.refresh(asset)
    return asset
