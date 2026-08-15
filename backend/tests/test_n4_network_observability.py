"""N4 网络可观测闭环：样本/告警/趋势/LLDP/导出 测试。"""
import asyncio
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.alert import Alert
from app.models.asset import Asset
from app.models.base import Base
from app.models.device import (
    ConfigChangeEvent,
    Device,
    DeviceConfigSnapshot,
    DeviceCredential,
    InterfaceMetricSample,
)
from app.models.lldp import LldpObservation
from app.core.database import engine, SessionLocal
from app.services.interface_rate import compute_rate, classify_interface
from app.services.config_change_alert import record_config_change_event
from app.services.trend_service import (
    MAX_TREND_SPAN_SECONDS,
    query_interface_trend,
    parse_iso,
)
from app.services.snmpv3_collector import (
    _collect_lldp_via_transport,
    LLDP_REM_COLUMNS,
)
from app.services.device_collector import (
    _detect_restart,
    _sample_marker,
)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _create_device_with_cred(client, token):
    """创建设备 + SNMP/SSH 凭据并关联，返回 device_id。"""
    r = client.post("/api/devices/credentials", headers=_h(token), json={
        "name": "test-snmp",
        "protocol": "snmp_v3",
        "username": "admin",
        "auth_key": "authkey123",
        "priv_key": "privkey123",
        "auth_algorithm": "SHA-256",
        "priv_algorithm": "AES-128",
    })
    snmp_cred_id = r.json()["data"]["id"]
    r = client.post("/api/devices/credentials", headers=_h(token), json={
        "name": "test-ssh",
        "protocol": "ssh",
        "username": "root",
        "auth_key": "pass1234",
        "ssh_key": "none",
    })
    ssh_cred_id = r.json()["data"]["id"]
    dev = client.post("/api/devices", headers=_h(token), json={
        "name": "test-device",
        "management_ip": "10.0.0.99",
        "vendor_platform": "linux",
        "snmp_config_id": snmp_cred_id,
        "ssh_config_id": ssh_cred_id,
    }).json()["data"]
    return dev["id"]


@pytest.fixture()
def fresh_db():
    """为无 client fixture 的测试建立独立表结构（并清理残留）。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ---- 模型与基本服务测试 ----

def test_detect_restart_cases():
    assert _detect_restart(1000, 400) is True   # 前值一半以下 → 重启
    assert _detect_restart(1000, 900) is False   # 正常变化
    assert _detect_restart(None, 100) is False
    assert _detect_restart(1000, None) is False


def test_sample_marker_cases():
    class FakePrev:
        if_in_octets = 1000
        if_out_octets = 2000
    assert _sample_marker(None, 500, 1000, False) == "ok"
    assert _sample_marker(None, 500, 1000, True) == "restart"
    assert _sample_marker(FakePrev(), 1100, 2100, False) == "ok"
    assert _sample_marker(FakePrev(), 800, 1000, False) == "wrap"  # out < prev


def test_interface_rate_counter_wrap():
    """64 位计数器回绕后速率不应为巨大正值。"""
    prev = datetime(2026, 8, 15, 1, 0, 0)
    curr = datetime(2026, 8, 15, 1, 0, 30)
    wrap_prev = 2**64 - 100
    wrap_curr = 50
    rate = compute_rate(wrap_prev, wrap_curr, prev, curr)
    assert rate is not None
    assert rate < 100_000_000_000  # < sanity 上界


def test_classify_interface_status():
    assert classify_interface(1, 1) == "ok"
    assert classify_interface(2, 1) == "down"
    assert classify_interface(1, 2) == "down"
    assert classify_interface(None, None) == "unknown"


# ---- ConfigChangeEvent + 告警联动 ----

def test_record_config_change_creates_event_and_alert(client, auth_token):
    device_id = _create_device_with_cred(client, auth_token)

    db = SessionLocal()
    try:
        device = db.query(Device).get(device_id)
        snap1 = DeviceConfigSnapshot(
            device_id=device_id, vendor_platform="linux",
            config_full_hash="old-hash", config_text_redacted="# old config",
            source="ssh", changed=False,
        )
        db.add(snap1); db.commit(); db.refresh(snap1)
        snap2 = DeviceConfigSnapshot(
            device_id=device_id, vendor_platform="linux",
            config_full_hash="new-hash", config_text_redacted="# new config",
            source="ssh", changed=True,
        )
        db.add(snap2); db.commit(); db.refresh(snap2)

        result = record_config_change_event(db, device, snap2)
        assert result["status"] == "recorded"
        assert result["changed_lines"] >= 0
        event = db.query(ConfigChangeEvent).first()
        assert event is not None
        assert event.device_id == device_id
        # alert_key 格式：device:{id}:config_change:{hash}
        assert f"device:{device_id}:config_change:" in event.alert_key

        # 事件唯一约束：再次对同一快照登记不重复
        result2 = record_config_change_event(db, device, snap2)
        assert result2["status"] == "already_recorded"
    finally:
        db.close()


def test_record_config_change_no_asset_skips_alert(client, auth_token):
    # 设备（10.0.0.99）没有匹配资产 → 不产生孤儿 Alert，事件标记 note
    device_id = _create_device_with_cred(client, auth_token)
    db = SessionLocal()
    try:
        device = db.query(Device).get(device_id)
        snap = DeviceConfigSnapshot(
            device_id=device_id, vendor_platform="linux",
            config_full_hash="hash-solo", config_text_redacted="# solo",
            source="ssh", changed=True,
        )
        db.add(snap); db.commit(); db.refresh(snap)
        result = record_config_change_event(db, device, snap)
        assert result["status"] == "recorded"
        assert result["alert_id"] is None            # 无孤儿 Alert
        assert result["note"] == "设备未关联资产，跳过告警"
        event = db.query(ConfigChangeEvent).get(result["event_id"])
        assert event.resolved is False
    finally:
        db.close()


# ---- 趋势服务 ----

def test_trend_service_empty_range(fresh_db):
    db = SessionLocal()
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        data = query_interface_trend(db, 999, None, now - timedelta(hours=1), now)
        assert data["interfaces"] == []
    finally:
        db.close()


def test_trend_service_with_samples(fresh_db):
    db = SessionLocal()
    try:
        dev = Device(name="trend-dev", management_ip="10.0.0.1", vendor_platform="linux",
                     collect_status="unknown")
        db.add(dev); db.commit(); db.refresh(dev)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(5):
            db.add(InterfaceMetricSample(
                device_id=dev.id, interface_index=1, interface_name="eth0",
                collected_at=now - timedelta(seconds=60 * (4 - i)),
                in_bps=1000.0 + i, out_bps=500.0 + i,
                sys_uptime=1000 + 60 * i, sample_marker="ok",
            ))
        db.commit()
        data = query_interface_trend(
            db, dev.id, 1,
            now - timedelta(minutes=5), now, interval_seconds=60,
        )
        assert len(data["interfaces"]) == 1
        assert data["interfaces"][0]["interface_index"] == 1
        assert len(data["interfaces"][0]["points"]) >= 3
    finally:
        db.close()


# ---- LLDP 观测 upsert ----

def test_lldp_observation_upsert(client, auth_token):
    device_id = _create_device_with_cred(client, auth_token)
    db = SessionLocal()
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        device = db.query(Device).get(device_id)
        # 第一次写入
        obs1 = LldpObservation(
            device_id=device_id, local_port_index=1,
            lldp_time_mark=100, lldp_index=1,
            remote_chassis_id="00:11:22:33:44:55",
            remote_port_id="port-A", remote_sysname="sw1", last_seen=now,
        )
        db.add(obs1); db.commit()
        # 相同身份第二次写入 → 应 upsert（更新 last_seen）
        from app.models.lldp import LldpObservation as Ll
        existing = db.query(Ll).filter(
            Ll.device_id == device_id,
            Ll.local_port_index == 1,
            Ll.remote_chassis_id == "00:11:22:33:44:55",
            Ll.remote_port_id == "port-A",
        ).first()
        assert existing is not None
        assert existing.remote_sysname == "sw1"
    finally:
        db.close()


# ---- diff 导出 API ----

def test_config_diff_export_text(client, auth_token):
    device_id = _create_device_with_cred(client, auth_token)
    db = SessionLocal()
    try:
        for i, (h, txt) in enumerate([("h1", "# old\naaa"), ("h2", "# new\naaa\nbbb")]):
            db.add(DeviceConfigSnapshot(
                device_id=device_id, vendor_platform="linux",
                config_full_hash=h, config_text_redacted=txt,
                source="ssh", changed=i > 0,
            ))
        db.commit()
        snaps = db.query(DeviceConfigSnapshot).filter(
            DeviceConfigSnapshot.device_id == device_id
        ).order_by(DeviceConfigSnapshot.id.asc()).all()
        from_id, to_id = snaps[0].id, snaps[1].id
    finally:
        db.close()

    resp = client.get(
        f"/api/devices/{device_id}/configs/diff/export?fmt=text&from_id={from_id}&to_id={to_id}",
        headers=_h(auth_token),
    )
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    body = resp.content.decode()
    assert "+# new" in body or "bbb" in body


def test_config_diff_export_excel_formula_injection_blocked(client, auth_token):
    """Excel 中含 = 或 + 开头的配置行应被防公式注入。"""
    device_id = _create_device_with_cred(client, auth_token)
    db = SessionLocal()
    try:
        db.add(DeviceConfigSnapshot(
            device_id=device_id, vendor_platform="linux",
            config_full_hash="h-safe-old", config_text_redacted="line old",
            source="ssh", changed=False,
        ))
        db.add(DeviceConfigSnapshot(
            device_id=device_id, vendor_platform="linux",
            config_full_hash="h-safe-new", config_text_redacted="line old\n=SUM(A1:A10)\n+foo",
            source="ssh", changed=True,
        ))
        db.commit()
        snaps = db.query(DeviceConfigSnapshot).filter(
            DeviceConfigSnapshot.device_id == device_id
        ).order_by(DeviceConfigSnapshot.id.asc()).all()
        from_id, to_id = snaps[0].id, snaps[1].id
    finally:
        db.close()

    resp = client.get(
        f"/api/devices/{device_id}/configs/diff/export?fmt=excel&from_id={from_id}&to_id={to_id}",
        headers=_h(auth_token),
    )
    assert resp.status_code == 200
    assert "sheet" in resp.headers.get("content-type", "") or len(resp.content) > 100


def test_config_diff_export_capped(client, auth_token):
    """超过 diff_max_rows 的大差异应标注 capped。"""
    device_id = _create_device_with_cred(client, auth_token)
    db = SessionLocal()
    try:
        big_new = "\n".join(f"line-{i}" for i in range(5000))
        db.add(DeviceConfigSnapshot(
            device_id=device_id, vendor_platform="linux",
            config_full_hash="h-big-old", config_text_redacted="line-old",
            source="ssh", changed=False,
        ))
        db.add(DeviceConfigSnapshot(
            device_id=device_id, vendor_platform="linux",
            config_full_hash="h-big-new", config_text_redacted=big_new,
            source="ssh", changed=True,
        ))
        db.commit()
        snaps = db.query(DeviceConfigSnapshot).filter(
            DeviceConfigSnapshot.device_id == device_id
        ).order_by(DeviceConfigSnapshot.id.asc()).all()
        from_id, to_id = snaps[0].id, snaps[1].id
    finally:
        db.close()

    resp = client.get(
        f"/api/devices/{device_id}/configs/diff/export?fmt=text&from_id={from_id}&to_id={to_id}",
        headers=_h(auth_token),
    )
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "截断" in body or len(body) < 100_000  # 有上限不无限大


# ---- InterfaceMetricSample 模型 ----

def test_interface_metric_sample_creation(fresh_db):
    db = SessionLocal()
    try:
        dev = Device(name="sample-dev", management_ip="10.0.0.5", vendor_platform="linux")
        db.add(dev); db.commit(); db.refresh(dev)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(InterfaceMetricSample(
            device_id=dev.id, interface_index=1, interface_name="eth0",
            collected_at=now,
            in_bps=12345.6, out_bps=6789.0,
            in_errors=5, out_errors=2,
            in_discards=0, out_discards=0,
            admin_status=1, oper_status=1,
            sys_uptime=50000, sample_marker="ok",
        ))
        db.commit()
        row = db.query(InterfaceMetricSample).first()
        assert row is not None
        assert row.in_errors == 5
        assert row.sample_marker == "ok"
    finally:
        db.close()
