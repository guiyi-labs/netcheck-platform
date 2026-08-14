"""设备采集编排器：Device → 凭据 → SNMPv3/SSH 采集 → 落库接口指标。

流程：
1. 按 device 的 snmp_config_id / ssh_config_id 读取凭据；
2. SNMPv3 采集 sys* + 接口表；SSH 采集 hostname/uname 等事实；
3. 接口速率用相邻样本（库里上一快照 + 当前采集时间）计算；
4. 落库 SnmpInterfaceMetric，更新 Device 采集状态与事实；
5. 失败分类写入 last_collect_error，绝不显示为健康。
"""
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.device import Device, DeviceCredential, SnmpInterfaceMetric
from app.models.asset import Asset
from app.services import credential_manager
from app.services.interface_rate import compute_rate, classify_interface, now_utc
from app.services.snmpv3_collector import run_snmpv3_sync
from app.services.ssh_collector import collect_ssh

logger = logging.getLogger("netcheck.device")

SNMP_FACT_MAP = {
    "sys_name": "sys_name",
    "sys_descr": "sys_descr",
    "sys_uptime": "sys_uptime",
}


def _load_credential(db: Session, credential_id: int | None) -> DeviceCredential | None:
    if not credential_id:
        return None
    return db.query(DeviceCredential).filter(DeviceCredential.id == credential_id).first()


def _decrypt_cred_fields(cred: DeviceCredential) -> dict:
    """解密凭据字段（无 secret key 时返回空，不抛异常）。"""
    out = {"auth_key": "", "priv_key": "", "ssh_key": ""}
    if cred is None:
        return out
    try:
        if cred.auth_key_encrypted:
            out["auth_key"] = credential_manager.decrypt_secret(cred.auth_key_encrypted)
        if cred.priv_key_encrypted:
            out["priv_key"] = credential_manager.decrypt_secret(cred.priv_key_encrypted)
        if cred.ssh_key_encrypted:
            out["ssh_key"] = credential_manager.decrypt_secret(cred.ssh_key_encrypted)
    except Exception as exc:
        logger.warning("凭据解密失败 credential_id=%s: %s", cred.id, exc)
        return {"auth_key": "", "priv_key": "", "ssh_key": "", "error": str(exc)}
    out["username"] = cred.username
    out["auth_algorithm"] = cred.auth_algorithm
    out["priv_algorithm"] = cred.priv_algorithm
    return out


def _purge_old_interfaces(db: Session, device_id: int, keep_latest: int = 3) -> None:
    """控制接口指标表增长：只保留每接口最近 keep_latest 个快照。"""
    # 简单策略：删除每设备超过上限的最老快照
    for metric in (
        db.query(SnmpInterfaceMetric)
        .filter(SnmpInterfaceMetric.device_id == device_id)
        .order_by(SnmpInterfaceMetric.id.desc())
        .offset(settings.snmp_max_interfaces * keep_latest)
        .all()
    ):
        db.delete(metric)


def _find_prev_metric(db: Session, device_id: int, index: int) -> SnmpInterfaceMetric | None:
    return (
        db.query(SnmpInterfaceMetric)
        .filter(
            SnmpInterfaceMetric.device_id == device_id,
            SnmpInterfaceMetric.interface_index == index,
        )
        .order_by(SnmpInterfaceMetric.collected_at.desc())
        .first()
    )


def _store_snmp_result(db: Session, device: Device, snmp_result) -> None:
    """把 SNMP 采集结果写库（接口指标 + 设备事实）。"""
    device.last_collected_at = now_utc()
    if snmp_result.status != "ok":
        device.collect_status = snmp_result.status
        device.last_collect_error = snmp_result.error or snmp_result.status
        logger.warning(
            "设备 %s SNMP 采集失败: %s", device.name, snmp_result.status
        )
        return

    # 设备事实
    for key, field in SNMP_FACT_MAP.items():
        if key in snmp_result.facts and snmp_result.facts[key]:
            setattr(device, field, snmp_result.facts[key])

    collected_at = now_utc()
    for entry in snmp_result.interfaces:
        idx = entry.get("index")
        if idx is None:
            continue
        prev = _find_prev_metric(db, device.id, idx)
        prev_in = prev.if_in_octets if prev else None
        prev_out = prev.if_out_octets if prev else None
        prev_at = prev.collected_at if prev else None
        in_rate = compute_rate(prev_in, entry.get("in_octets"), prev_at, collected_at)
        out_rate = compute_rate(prev_out, entry.get("out_octets"), prev_at, collected_at)
        metric = SnmpInterfaceMetric(
            device_id=device.id,
            interface_index=idx,
            interface_name=entry.get("name", f"if{idx}"),
            interface_descr=None,
            admin_status=entry.get("admin_status"),
            oper_status=entry.get("oper_status"),
            if_speed=entry.get("if_speed"),
            if_in_octets=entry.get("in_octets"),
            if_out_octets=entry.get("out_octets"),
            in_rate_bps=in_rate,
            out_rate_bps=out_rate,
            prev_in_octets=prev_in,
            prev_out_octets=prev_out,
            prev_collected_at=prev_at,
            status=classify_interface(entry.get("admin_status"), entry.get("oper_status")),
            collected_at=collected_at,
        )
        db.add(metric)
    device.collect_status = "success"
    device.last_collect_error = None
    _purge_old_interfaces(db, device.id)


def _run_ssh_collection(db: Session, device: Device, cred: DeviceCredential | None) -> None:
    """执行 SSH 只读采集（同步，内部 async 包装）。"""
    import asyncio

    key_pem = ""
    password = None
    if cred is not None:
        fields = _decrypt_cred_fields(cred)
        key_pem = fields.get("ssh_key", "")
        password = fields.get("auth_key", "") or None  # SSH 密码存于 auth_key 字段
    result = asyncio.run(
        collect_ssh(
            host=device.management_ip,
            port=22,
            username=cred.username if cred else "root",
            password=password,
            key_pem=key_pem or None,
            vendor=device.vendor_platform,
            host_key_fingerprint=device.host_key_fingerprint,
        )
    )
    if result.status == "ok":
        for key, value in result.facts.items():
            if key == "hostname":
                device.hostname = value
            elif key in ("os_type", "os_version"):
                if key == "os_version":
                    device.os_version = value
        device.last_collected_at = now_utc()
        device.collect_status = "success"
        device.last_collect_error = None
        device.host_key_fingerprint = result.host_key_fingerprint or device.host_key_fingerprint
        # 暂存原始证据（脱敏后）到日志
        logger.info(
            "SSH 采集完成 %s: %s", device.name, list(result.raw_outputs.keys())
        )
    else:
        device.collect_status = result.status
        device.last_collect_error = result.error or result.status


def collect_device(db: Session, device: Device, only_ssh: bool = False) -> dict:
    """采集单台设备（SNMPv3 + 可选 SSH）。返回简洁状态（无凭据）。"""
    if device.collect_status == "collecting":
        return {"id": device.id, "status": "collecting", "error": "正在采集中"}

    device.collect_status = "collecting"
    db.commit()

    results = {"protocols": {}, "snmp": None, "ssh": None}

    # ---- SNMPv3 ----
    if not only_ssh and device.snmp_config_id:
        cred = _load_credential(db, device.snmp_config_id)
        fields = _decrypt_cred_fields(cred)
        if cred is None or not fields.get("auth_key"):
            device.collect_status = "error"
            device.last_collect_error = "缺少 SNMPv3 凭据或密钥无法解密"
            db.commit()
            return {
                "id": device.id, "status": "error",
                "error": "缺少 SNMPv3 凭据或密钥无法解密",
            }
        snmp_result = run_snmpv3_sync(
            device.management_ip,
            fields["username"],
            fields.get("auth_key", ""),
            fields.get("priv_key", ""),
            fields.get("auth_algorithm", "SHA-256"),
            fields.get("priv_algorithm", "AES-128"),
        )
        results["snmp"] = snmp_result.status
        if snmp_result.status == "ok":
            _store_snmp_result(db, device, snmp_result)
        else:
            device.collect_status = snmp_result.status
            device.last_collect_error = snmp_result.error or snmp_result.status
            db.commit()
            return {
                "id": device.id, "status": snmp_result.status,
                "error": snmp_result.error or snmp_result.status,
            }

    # ---- SSH ----
    if device.ssh_config_id:
        cred = _load_credential(db, device.ssh_config_id)
        _run_ssh_collection(db, device, cred)

    results["status"] = device.collect_status
    db.commit()
    return {
        "id": device.id,
        "status": device.collect_status,
        "error": device.last_collect_error,
        "last_collected_at": (
            device.last_collected_at.isoformat() if device.last_collected_at else None
        ),
    }


def collect_devices(db: Session, device_ids: list[int]) -> list[dict]:
    """批量采集（默认按配置全部采集），有界上限。"""
    if not device_ids:
        return []
    if len(device_ids) > settings.device_collect_max_batch:
        device_ids = device_ids[: settings.device_collect_max_batch]
    results = []
    for device_id in device_ids:
        device = db.query(Device).filter(Device.id == device_id).first()
        if device is None:
            results.append({"id": device_id, "status": "error", "error": "设备不存在"})
            continue
        results.append(collect_device(db, device))
    return results