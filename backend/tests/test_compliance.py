"""N2.2 配置合规基线：is_baseline 标记唯一性 + 合规报告（行级 diff 粒度）。

- 粒度如实标注：行级 diff（非语义级）。
- 用例为 mock DB（TestClient + 临时 SQLite），无真实设备依赖。
"""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.models.device import Device, DeviceConfigSnapshot


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mk_device(client: TestClient, token: str, name: str = "compliance-test") -> int:
    resp = client.post(
        "/api/devices",
        json={"name": name, "management_ip": "192.168.99.99", "vendor": "generic"},
        headers=_h(token),
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["data"]["id"]


def _mk_snapshot(device_id: int, text: str, is_baseline: bool = False) -> DeviceConfigSnapshot:
    db = SessionLocal()
    try:
        snap = DeviceConfigSnapshot(
            device_id=device_id,
            vendor_platform="generic",
            config_full_hash=f"hash-{text}",
            config_text_redacted=text,
            source="ssh",
            changed=False,
            truncated=False,
            is_baseline=is_baseline,
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        return snap
    finally:
        db.close()


# ---------- 服务层：set_baseline ----------

def test_set_baseline_marks_snapshot(client: TestClient, auth_token):
    """标记基线：快照 is_baseline=True。"""
    dev_id = _mk_device(client, auth_token)
    snap = _mk_snapshot(dev_id, "hostname core\n")

    from app.services.compliance import set_baseline

    db = SessionLocal()
    try:
        updated = set_baseline(db, dev_id, snap.id, enabled=True)
        assert updated is not None
        assert updated.is_baseline is True
    finally:
        db.close()


def test_set_baseline_uniqueness_per_device(client: TestClient, auth_token):
    """同设备基线唯一：标记第二个快照后，第一个自动取消。"""
    dev_id = _mk_device(client, auth_token)
    s1 = _mk_snapshot(dev_id, "hostname core\n")
    s2 = _mk_snapshot(dev_id, "hostname core-2\n")

    from app.services.compliance import set_baseline

    db = SessionLocal()
    try:
        set_baseline(db, dev_id, s1.id)
        set_baseline(db, dev_id, s2.id)
        db.expire_all()
        first = db.get(DeviceConfigSnapshot, s1.id)
        second = db.get(DeviceConfigSnapshot, s2.id)
        assert first.is_baseline is False
        assert second.is_baseline is True
    finally:
        db.close()


def test_set_baseline_unclear(client: TestClient, auth_token):
    """取消基线：enabled=False 清除标记。"""
    dev_id = _mk_device(client, auth_token)
    snap = _mk_snapshot(dev_id, "hostname core\n", is_baseline=True)

    from app.services.compliance import set_baseline

    db = SessionLocal()
    try:
        updated = set_baseline(db, dev_id, snap.id, enabled=False)
        assert updated.is_baseline is False
    finally:
        db.close()


def test_set_baseline_missing_snapshot(client: TestClient, auth_token):
    """快照不存在 → 返回 None（API 404）。"""
    dev_id = _mk_device(client, auth_token)

    from app.services.compliance import set_baseline

    db = SessionLocal()
    try:
        assert set_baseline(db, dev_id, 999999, enabled=True) is None
    finally:
        db.close()


# ---------- 服务层：get_compliance_report ----------

def test_compliance_pass_no_changes(client: TestClient, auth_token):
    """合规通过：最新快照即为基线（无后续变更）→ status=pass。"""
    dev_id = _mk_device(client, auth_token)
    s1 = _mk_snapshot(dev_id, "hostname core\ninterface GE0/1\n", is_baseline=True)

    from app.services.compliance import get_compliance_report

    db = SessionLocal()
    try:
        report = get_compliance_report(db, dev_id)
        assert report["status"] == "pass"
        assert report["failed"] == 0
        assert report["baseline_id"] == s1.id
        assert report["current_id"] == s1.id
    finally:
        db.close()


def test_compliance_warn_small_diff(client: TestClient, auth_token):
    """合规警告：少量变更（≤10 行）→ status=warn。"""
    dev_id = _mk_device(client, auth_token)
    _mk_snapshot(dev_id, "hostname core\ninterface GE0/1\nip route 0.0.0.0\n", is_baseline=True)
    _mk_snapshot(dev_id, "hostname core\ninterface GE0/1\nip route 10.0.0.0\n")

    from app.services.compliance import get_compliance_report

    db = SessionLocal()
    try:
        report = get_compliance_report(db, dev_id)
        assert report["status"] == "warn"
        assert report["failed"] == 2  # 一条变更行涉及 del+add
    finally:
        db.close()


def test_compliance_fail_large_diff(client: TestClient, auth_token):
    """合规失败：大量变更（>10 行）→ status=fail。"""
    dev_id = _mk_device(client, auth_token)
    baseline_lines = [f"config line {i}" for i in range(6)]
    _mk_snapshot(dev_id, "\n".join(baseline_lines), is_baseline=True)
    changed_lines = [f"config line {i} changed" for i in range(6)]
    _mk_snapshot(dev_id, "\n".join(changed_lines))

    from app.services.compliance import get_compliance_report

    db = SessionLocal()
    try:
        report = get_compliance_report(db, dev_id)
        assert report["status"] == "fail"
        assert report["failed"] > 10
    finally:
        db.close()


def test_compliance_no_baseline_warns(client: TestClient, auth_token):
    """无基线：status=warn，detail 提示先标记基线。"""
    dev_id = _mk_device(client, auth_token)
    _mk_snapshot(dev_id, "hostname core\n")

    from app.services.compliance import get_compliance_report

    db = SessionLocal()
    try:
        report = get_compliance_report(db, dev_id)
        assert report["status"] == "warn"
        assert "基线" in report["status_detail"]
    finally:
        db.close()


# ---------- API 层 ----------

def test_api_baseline_endpoint(client: TestClient, auth_token):
    """API：POST baseline 标记成功，返回快照含 is_baseline=True。"""
    dev_id = _mk_device(client, auth_token)
    snap = _mk_snapshot(dev_id, "hostname core\n")

    resp = client.post(
        f"/api/devices/{dev_id}/configs/{snap.id}/baseline",
        headers=_h(auth_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_baseline"] is True


def test_api_baseline_404(client: TestClient, auth_token):
    """API：快照不存在 → 404。"""
    dev_id = _mk_device(client, auth_token)
    resp = client.post(
        f"/api/devices/{dev_id}/configs/999999/baseline",
        headers=_h(auth_token),
    )
    assert resp.status_code == 404


def test_api_compliance_endpoint(client: TestClient, auth_token):
    """API：GET compliance 返回结构化报告（pass 场景）。"""
    dev_id = _mk_device(client, auth_token)
    _mk_snapshot(dev_id, "hostname core\ninterface GE0/1\n", is_baseline=True)

    resp = client.get(
        f"/api/devices/{dev_id}/configs/compliance",
        headers=_h(auth_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "pass"
    assert data["passed"] == data["total_rules"]


def test_api_compliance_requires_operator(client: TestClient, auth_token):
    """API：合规报告仅 operator/admin 可读（viewer → 403）。"""
    dev_id = _mk_device(client, auth_token)
    _mk_snapshot(dev_id, "hostname core\n", is_baseline=True)

    # 创建 viewer 角色用户并登录
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200
    admin_token = login.json()["data"]["token"]
    create_user = client.post(
        "/api/users",
        json={"username": "viewer1", "password": "viewerpass123", "role": "viewer"},
        headers=_h(admin_token),
    )
    assert create_user.status_code in (200, 201), create_user.text
    vlogin = client.post(
        "/api/auth/login",
        json={"username": "viewer1", "password": "viewerpass123"},
    )
    assert vlogin.status_code == 200
    viewer_token = vlogin.json()["data"]["token"]

    resp = client.get(
        f"/api/devices/{dev_id}/configs/compliance",
        headers=_h(viewer_token),
    )
    assert resp.status_code == 403