"""N1 设备 API 集成测试：凭据 CRUD（无密钥回显）、设备 CRUD、采集触发、脱敏。"""
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.device import Device, DeviceCredential


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------- 凭据 ----------

def test_create_credential_encrypted_not_echoed(client, auth_token):
    resp = client.post(
        "/api/devices/credentials",
        headers=_h(auth_token),
        json={
            "name": "core-snmp",
            "protocol": "snmp_v3",
            "username": "monitor",
            "auth_key": "AuthKeySecret123",
            "priv_key": "PrivKeySecret456",
            "auth_algorithm": "SHA-256",
            "priv_algorithm": "AES-128",
        },
    )
    assert resp.status_code == 201
    body = resp.text
    assert "AuthKeySecret123" not in body
    assert "PrivKeySecret456" not in body
    data = resp.json()["data"]
    assert data["has_secret"] is True
    assert data["username"] == "monitor"


def test_create_credential_requires_admin(client, auth_token):
    """operator 不能建凭据（require_admin）。"""
    # 创建 operator 用户
    client.post(
        "/api/users", headers=_h(auth_token),
        json={"username": "op1", "password": "password123", "role": "operator"},
    )
    login = client.post("/api/auth/login", json={"username": "op1", "password": "password123"})
    op_token = login.json()["data"]["token"]

    resp = client.post(
        "/api/devices/credentials",
        headers=_h(op_token),
        json={"name": "x", "protocol": "snmp_v3", "username": "u"},
    )
    assert resp.status_code == 403


def test_credential_encrypted_at_rest(client, auth_token):
    """数据库里存的是密文而非明文。"""
    client.post(
        "/api/devices/credentials",
        headers=_h(auth_token),
        json={
            "name": "core-ssh",
            "protocol": "ssh",
            "username": "admin",
            "auth_key": "SSHPasswordRich1",
        },
    )
    db = SessionLocal()
    try:
        cred = db.query(DeviceCredential).filter(DeviceCredential.name == "core-ssh").first()
        assert cred is not None
        assert "SSHPasswordRich1" not in (cred.auth_key_encrypted or "")
        assert cred.auth_key_encrypted != ""
    finally:
        db.close()


def test_list_credentials_masks_secrets(client, auth_token):
    client.post(
        "/api/devices/credentials",
        headers=_h(auth_token),
        json={"name": "c1", "protocol": "snmp_v3", "username": "u",
              "auth_key": "S3cretAuth", "priv_key": "S3cretPriv"},
    )
    resp = client.get("/api/devices/credentials", headers=_h(auth_token))
    body = resp.text
    assert "S3cretAuth" not in body
    assert "S3cretPriv" not in body
    assert resp.json()["data"]["items"][0]["has_secret"] is True


# ---------- 设备 ----------

def test_create_device_and_get(client, auth_token):
    resp = client.post(
        "/api/devices",
        headers=_h(auth_token),
        json={
            "name": "core-router-01",
            "management_ip": "10.0.0.1",
            "vendor_platform": "linux",
        },
    )
    assert resp.status_code == 201
    device_id = resp.json()["data"]["id"]

    detail = client.get(f"/api/devices/{device_id}", headers=_h(auth_token))
    assert detail.status_code == 200
    assert detail.json()["data"]["collect_status"] == "idle"
    assert detail.json()["data"]["has_snmp"] is False


def test_update_device_binds_credentials(client, auth_token):
    cred = client.post(
        "/api/devices/credentials",
        headers=_h(auth_token),
        json={"name": "bind-snmp", "protocol": "snmp_v3", "username": "u",
              "auth_key": "authk1", "priv_key": "privk1"},
    ).json()["data"]
    dev = client.post(
        "/api/devices",
        headers=_h(auth_token),
        json={"name": "d1", "management_ip": "10.0.0.2", "vendor_platform": "generic"},
    ).json()["data"]
    resp = client.put(
        f"/api/devices/{dev['id']}",
        headers=_h(auth_token),
        json={
            "name": "d1", "management_ip": "10.0.0.2",
            "vendor_platform": "generic",
            "snmp_config_id": cred["id"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["has_snmp"] is True


def test_viewer_cannot_create_device(client, auth_token):
    client.post(
        "/api/users", headers=_h(auth_token),
        json={"username": "view1", "password": "password123", "role": "viewer"},
    )
    view_token = client.post(
        "/api/auth/login", json={"username": "view1", "password": "password123"}
    ).json()["data"]["token"]
    resp = client.post(
        "/api/devices", headers=_h(view_token),
        json={"name": "v", "management_ip": "10.0.0.3", "vendor_platform": "generic"},
    )
    assert resp.status_code == 403


def test_delete_device_cleans_metrics(client, auth_token):
    dev = client.post(
        "/api/devices",
        headers=_h(auth_token),
        json={"name": "rm-me", "management_ip": "10.0.0.4", "vendor_platform": "linux"},
    ).json()["data"]
    db = SessionLocal()
    try:
        from app.models.device import SnmpInterfaceMetric

        db.add(SnmpInterfaceMetric(
            device_id=dev["id"], interface_index=1, interface_name="eth0"))
        db.commit()
    finally:
        db.close()
    resp = client.delete(f"/api/devices/{dev['id']}", headers=_h(auth_token))
    assert resp.status_code == 200
    db = SessionLocal()
    try:
        from app.models.device import SnmpInterfaceMetric

        assert db.query(SnmpInterfaceMetric).filter(
            SnmpInterfaceMetric.device_id == dev["id"]).count() == 0
    finally:
        db.close()


# ---------- 采集触发（mock 采集） ----------

def test_collect_device_missing_credential_reports_error(client, auth_token, monkeypatch):
    """设备配置了 SNMP 凭据但凭据缺失 → 明确错误，不显示健康。"""
    dev = client.post(
        "/api/devices",
        headers=_h(auth_token),
        json={"name": "no-cred", "management_ip": "10.0.0.9", "vendor_platform": "generic",
              "snmp_config_id": 999},
    ).json()["data"]
    resp = client.post(f"/api/devices/{dev['id']}/collect", headers=_h(auth_token))
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] in ("error", "auth_failed", "timeout")


def test_collect_device_success_with_mocked_snmp(client, auth_token, monkeypatch):
    """SNMP 采集成功 + 接口指标落库 + 速率计算。"""
    cred_resp = client.post(
        "/api/devices/credentials",
        headers=_h(auth_token),
        json={"name": "ok-snmp", "protocol": "snmp_v3", "username": "monitor",
              "auth_key": "authk", "priv_key": "privk"},
    )
    cred_id = cred_resp.json()["data"]["id"]
    dev = client.post(
        "/api/devices",
        headers=_h(auth_token),
        json={"name": "ok-dev", "management_ip": "10.0.0.10",
              "vendor_platform": "generic", "snmp_config_id": cred_id},
    ).json()["data"]

    # mock SNMP 采集成功
    def fake_run_snmpv3(host, username, auth_key, priv_key, auth_algo="SHA-256",
                        priv_algo="AES-128", port=161):
        from app.services.snmpv3_collector import SnmpResult

        return SnmpResult(
            status="ok",
            facts={"sys_name": "router1", "sys_descr": "Test Router",
                   "sys_uptime": "12345"},
            interfaces=[
                {"index": 1, "name": "eth0", "admin_status": 1, "oper_status": 1,
                 "if_speed": 1000000000, "in_octets": 1000000, "out_octets": 2000000},
            ],
        )

    monkeypatch.setattr(
        "app.services.device_collector.run_snmpv3_sync", fake_run_snmpv3)

    resp = client.post(f"/api/devices/{dev['id']}/collect", headers=_h(auth_token))
    assert resp.status_code == 200
    status_data = resp.json()["data"]
    assert status_data["status"] == "success"

    detail = client.get(f"/api/devices/{dev['id']}", headers=_h(auth_token)).json()["data"]
    assert detail["sys_name"] == "router1"
    assert detail["collect_status"] == "success"

    interfaces = client.get(
        f"/api/devices/{dev['id']}/interfaces", headers=_h(auth_token)).json()["data"]
    assert len(interfaces) >= 1
    first = interfaces[0]
    assert first["interface_name"] == "eth0"
    assert first["status"] == "ok"
    assert first["in_rate_bps"] is None  # 首样本无速率 → unknown


def test_collect_device_snmp_failure_sets_status(client, auth_token, monkeypatch):
    """SNMP 认证失败 → 设备状态 auth_failed + 错误消息。"""
    cred = client.post(
        "/api/devices/credentials",
        headers=_h(auth_token),
        json={"name": "bad-snmp", "protocol": "snmp_v3", "username": "u",
              "auth_key": "authk", "priv_key": "privk"},
    ).json()["data"]
    dev = client.post(
        "/api/devices",
        headers=_h(auth_token),
        json={"name": "bad-dev", "management_ip": "10.0.0.11",
              "vendor_platform": "generic", "snmp_config_id": cred["id"]},
    ).json()["data"]

    def fake_run_snmpv3(host, username, auth_key, priv_key, auth_algo="SHA-256",
                        priv_algo="AES-128", port=161):
        from app.services.snmpv3_collector import SnmpResult

        return SnmpResult(status="auth_failed", error="认证失败")

    monkeypatch.setattr(
        "app.services.device_collector.run_snmpv3_sync", fake_run_snmpv3)

    resp = client.post(f"/api/devices/{dev['id']}/collect", headers=_h(auth_token))
    assert resp.json()["data"]["status"] == "auth_failed"

    detail = client.get(
        f"/api/devices/{dev['id']}", headers=_h(auth_token)).json()["data"]
    assert detail["collect_status"] == "auth_failed"
    assert "认证失败" in (detail["last_collect_error"] or "")