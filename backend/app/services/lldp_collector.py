"""N4 LLDP 邻居采集：复用 SNMPv3 采集器的 pysnmp 传输/用户构造（mock 友好）。

- 通过 `snmpv3_collector.collect_lldp / run_lldp_sync` 执行 lldpRemTable WALK；
- 索引语义 (lldpRemTimeMark, lldpRemLocalPortNum, lldpRemIndex) 由采集层解析；
- 本模块负责把邻居观测写入 `LldpObservation`（append-only 观测事实）。
"""
import logging

from sqlalchemy.orm import Session

from app.models.lldp import LldpObservation
from app.services import credential_manager
from app.services.device_collector import _decrypt_cred_fields, _load_credential
from app.services.snmpv3_collector import run_lldp_sync

logger = logging.getLogger("netcheck.lldp")


def collect_lldp_neighbors(db: Session, device, max_rows: int = 64) -> dict:
    """对单台设备采集 LLDP 邻居并写入观察表。

    返回 {"status": ..., "neighbors": N, "stored": M, "error": ...}
    """
    if not device.snmp_config_id:
        return {"status": "skipped", "error": "未配置 SNMPv3 凭据"}
    cred = _load_credential(db, device.snmp_config_id)
    fields = _decrypt_cred_fields(cred)
    if cred is None or not fields.get("auth_key"):
        return {"status": "error", "error": "缺少 SNMPv3 凭据或密钥无法解密"}

    result = run_lldp_sync(
        device.management_ip,
        fields["username"],
        fields.get("auth_key", ""),
        fields.get("priv_key", ""),
        fields.get("auth_algorithm", "SHA-256"),
        fields.get("priv_algorithm", "AES-128"),
        max_rows=max_rows,
    )
    if result.get("status") != "ok":
        return {
            "status": result.get("status", "error"),
            "neighbors": 0,
            "stored": 0,
            "error": result.get("error"),
        }

    neighbors = result.get("neighbors", []) or []
    stored = 0
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for n in neighbors:
        local_port = n.get("local_port")
        if local_port is None:
            continue
        chassis_id = (n.get("chassis_id") or "").strip()
        port_id = (n.get("port_id") or "").strip()
        # 同一邻居（同端口+同远端标识）连续采集 → upsert 更新 last_seen
        existing = (
            db.query(LldpObservation)
            .filter(
                LldpObservation.device_id == device.id,
                LldpObservation.local_port_index == local_port,
                LldpObservation.remote_chassis_id == chassis_id,
                LldpObservation.remote_port_id == port_id,
            )
            .first()
        )
        if existing is not None:
            existing.remote_sysname = n.get("sysname") or existing.remote_sysname
            existing.remote_sysdesc = n.get("sysdesc") or existing.remote_sysdesc
            existing.remote_chassis_subtype = n.get("chassis_subtype") or existing.remote_chassis_subtype
            existing.remote_port_subtype = n.get("port_subtype") or existing.remote_port_subtype
            existing.lldp_time_mark = n.get("time_mark", existing.lldp_time_mark)
            existing.lldp_index = n.get("lldp_index", existing.lldp_index)
            existing.last_seen = now
            stored += 1
            continue
        obs = LldpObservation(
            device_id=device.id,
            local_port_index=local_port,
            local_port_name=n.get("local_port_name"),
            lldp_time_mark=n.get("time_mark", 0),
            lldp_index=n.get("lldp_index", 1),
            remote_chassis_subtype=n.get("chassis_subtype"),
            remote_chassis_id=chassis_id,
            remote_port_subtype=n.get("port_subtype"),
            remote_port_id=port_id,
            remote_sysname=n.get("sysname"),
            remote_sysdesc=n.get("sysdesc"),
            last_seen=now,
        )
        db.add(obs)
        stored += 1
    if stored:
        db.commit()
    return {"status": "ok", "neighbors": len(neighbors), "stored": stored}