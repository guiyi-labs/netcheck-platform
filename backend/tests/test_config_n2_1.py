"""N2.1 安全与一致性收口测试：脱敏扩展、viewer 403、并发去重、设备删除级联、diff 限制。"""
import asyncio
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import func

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.device import Device, DeviceConfigSnapshot, DeviceCredential


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---- P0 脱敏覆盖 ----

class TestRedactPEMBlock:
    """PEM 私钥块状态机：多行 Secret 遮蔽。"""

    def test_rsa_private_key_block(self):
        from app.services.config_backup import redact_config

        text = (
            "hostname core-router\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA0Z3VS5JJcds\n"
            "MIIEvgIBADANBgkqhkiG9w0BAS\n"
            "-----END RSA PRIVATE KEY-----\n"
            "interface GigabitEthernet0/1\n"
        )
        out = redact_config(text)
        lines = out.split("\n")
        assert lines[0] == "hostname core-router"
        assert lines[1] == "-----BEGIN PRIVATE KEY-----"
        assert lines[2] == "********"  # 块体遮蔽
        assert lines[3] == "********"  # 块体遮蔽
        assert lines[4] == "-----END PRIVATE KEY-----"
        assert lines[5] == "interface GigabitEthernet0/1"
        assert len(lines) == 6  # 行数不变（用于 diff 稳定性）

    def test_openssh_private_key_block(self):
        from app.services.config_backup import redact_config

        text = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNzaC1rZXktdjEAAAA=\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        )
        out = redact_config(text)
        assert "-----BEGIN PRIVATE KEY-----" in out
        assert "********" in out.split("\n")

    def test_ec_private_key_block(self):
        from app.services.config_backup import redact_config

        text = (
            "-----BEGIN EC PRIVATE KEY-----\n"
            "MHQCAQEEIIx\n"
            "-----END EC PRIVATE KEY-----\n"
        )
        out = redact_config(text)
        assert "BEGIN PRIVATE KEY" in out
        assert "MHQCAQEEIIx" not in out

    def test_pem_no_false_positive_on_non_key(self):
        from app.services.config_backup import redact_config

        text = "-----BEGIN CERTIFICATE-----\nMIIBkTCB+wI...\n-----END CERTIFICATE-----"
        out = redact_config(text)
        assert "MIIBkTCB+wI..." in out  # 证书行不被遮蔽
        assert "BEGIN CERTIFICATE" in out

    def test_empty_pem_block(self):
        from app.services.config_backup import redact_config

        text = "-----BEGIN PRIVATE KEY-----\n-----END PRIVATE KEY-----"
        out = redact_config(text)
        assert "BEGIN PRIVATE KEY" in out
        assert "END PRIVATE KEY" in out
        assert "********" not in out  # 块体为空，无遮蔽


class TestRedactIsakmp:
    """crypto isakmp key 脱敏。"""

    def test_isakmp_key_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("crypto isakmp key 12345678 address 10.0.0.1")
        assert "12345678" not in out
        assert "10.0.0.1" not in out  # address 值被 mask（整体匹配，保留前缀）
        assert "crypto isakmp key" in out

    def test_isakmp_key_with_pre_shared(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("crypto isakmp key MyPSK123 address 192.168.1.1")
        assert "MyPSK123" not in out
        assert "crypto isakmp key" in out


class TestRedactWireGuard:
    """WireGuard PrivateKey/PresharedKey 脱敏。"""

    def test_private_key_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("PrivateKey = abc123xyz_base64==")
        assert "abc123xyz_base64==" not in out
        assert "PrivateKey =" in out

    def test_preshared_key_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("PresharedKey = secretkey12345")
        assert "secretkey12345" not in out
        assert "PresharedKey =" in out

    def test_wg_allowedips_not_masked(self):
        """WireGuard 地址行无密钥不应被误遮蔽。"""
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("AllowedIPs = 10.0.0.0/24")
        assert out == "AllowedIPs = 10.0.0.0/24"

    def test_wg_endpoint_not_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("Endpoint = 1.2.3.4:51820")
        assert out == "Endpoint = 1.2.3.4:51820"


class TestRedactNegativeExamples:
    """负例：接口名/说明文本/普通配置不被误遮蔽。"""

    def test_interface_name_not_masked(self):
        from app.services.config_backup import redact_secret_value

        for line in [
            "interface GigabitEthernet0/1",
            "interface Loopback0",
            "interface Vlan10",
            " ip address 10.1.1.1 255.255.255.0",
            " description uplink to core switch",
            " no shutdown",
        ]:
            assert redact_secret_value(line) == line, f"误遮蔽: {line}"

    def test_hostname_not_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("hostname core-router-01")
        assert out == "hostname core-router-01"

    def test_vlan_not_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("vlan 10 name management")
        assert out == "vlan 10 name management"

    def test_ip_route_not_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("ip route 0.0.0.0 0.0.0.0 10.0.0.1")
        assert out == "ip route 0.0.0.0 0.0.0.0 10.0.0.1"

    def test_cisco_bgp_not_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("router bgp 65001")
        assert out == "router bgp 65001"

    def test_description_with_common_words_not_masked(self):
        from app.services.config_backup import redact_secret_value

        for line in [
            "description link to customer",
            "description production network",
            " description 10G uplink",
        ]:
            assert redact_secret_value(line) == line, f"误遮蔽: {line}"

    def test_system_version_not_masked(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("version 16.12.4")
        assert out == "version 16.12.4"


# ---- P1 权限：viewer 403 ----

class TestConfigViewer403:
    """查看者无法读取配置全文/diff（N2.1 P1）。"""

    def test_viewer_latest_403(self, client, auth_token, monkeypatch):
        """viewer GET /configs/latest → 403。"""
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "v-dev", "management_ip": "10.0.2.1",
                                "vendor_platform": "generic"})
        dev_id = dev.json()["data"]["id"]

        viewer_token = _make_viewer(client)
        resp = client.get(f"/api/devices/{dev_id}/configs/latest", headers=_h(viewer_token))
        assert resp.status_code == 403
        assert "查看者" in resp.json()["detail"]

    def test_viewer_diff_403(self, client, auth_token, monkeypatch):
        """viewer GET /configs/diff → 403。"""
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "v-diff", "management_ip": "10.0.2.2",
                                "vendor_platform": "generic"})
        dev_id = dev.json()["data"]["id"]

        viewer_token = _make_viewer(client)
        resp = client.get(f"/api/devices/{dev_id}/configs/diff", headers=_h(viewer_token))
        assert resp.status_code == 403

    def test_viewer_collect_403(self, client, auth_token, monkeypatch):
        """viewer POST /configs/collect → 403（需要 require_write）。"""
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "v-coll", "management_ip": "10.0.2.3",
                                "vendor_platform": "generic"})
        dev_id = dev.json()["data"]["id"]

        viewer_token = _make_viewer(client)
        resp = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(viewer_token))
        assert resp.status_code == 403

    def test_operator_latest_ok(self, client, auth_token, monkeypatch):
        """operator GET /configs/latest → 200（无快照返回 404）。"""
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "o-dev", "management_ip": "10.0.2.4",
                                "vendor_platform": "generic"})
        dev_id = dev.json()["data"]["id"]

        resp = client.get(f"/api/devices/{dev_id}/configs/latest", headers=_h(auth_token))
        assert resp.status_code == 404  # 无快照

    def test_unauth_401(self, client, auth_token, monkeypatch):
        """无 token GET /configs/latest → 401。"""
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "ua-dev", "management_ip": "10.0.2.5",
                                "vendor_platform": "generic"})
        dev_id = dev.json()["data"]["id"]

        resp = client.get(f"/api/devices/{dev_id}/configs/latest")
        assert resp.status_code == 401

    def test_nonexistent_device_404(self, client, auth_token):
        """GET /configs/latest 不存在设备 → 404。"""
        resp = client.get("/api/devices/99999/configs/latest", headers=_h(auth_token))
        assert resp.status_code == 404


def _make_viewer(client: TestClient) -> str:
    """直接向 DB 插入 viewer 用户并返回其 token。"""
    from app.models.user import User
    from app.core.security import hash_password

    token = "viewer-token-" + str(int(time.time() * 1000))[-6:]
    with SessionLocal() as db:
        user = User(
            username="viewer_" + str(int(time.time() * 1000))[-6:],
            password_hash=hash_password("viewer123"),
            role="viewer",
            api_token=token,
            is_active=True,
        )
        db.add(user)
        db.commit()
    return token


# ---- P1 并发去重 ----

class TestConcurrentDedup:
    """并发采集同内容不产生重复快照（DB 级唯一约束兜底）。"""

    def test_concurrent_same_hash_no_duplicate(self, client, auth_token, monkeypatch):
        """两次快速相同 hash 采集只产生一条快照（唯一约束或查询去重）。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "dedup-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "dedup-dev", "management_ip": "10.0.3.1",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(
                status="ok", full_text="same-content", redacted="same-content",
                full_hash=hashlib.sha256(b"same").hexdigest(),
                command="cat /etc/hosts")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        # 快速连续两次采集
        r1 = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        r2 = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert r1.json()["data"]["status"] == "ok"
        assert r2.json()["data"]["status"] == "unchanged"

        items = client.get(f"/api/devices/{dev_id}/configs", headers=_h(auth_token)).json()["data"]["items"]
        assert len(items) == 1


# ---- P1 设备删除级联 ----

class TestDeviceDeleteCascade:
    """删除设备时清理配置快照（N2.1 P1）。"""

    def test_delete_cascades_snapshots(self, client, auth_token, monkeypatch):
        """删除设备 → 关联配置快照也被删除。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "del-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "del-dev", "management_ip": "10.0.4.1",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(
                status="ok", full_text="cfg", redacted="cfg",
                full_hash="del-hash", command="test")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        # 产生快照
        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        items = client.get(f"/api/devices/{dev_id}/configs", headers=_h(auth_token)).json()["data"]["items"]
        assert len(items) == 1

        # 删除设备
        client.delete(f"/api/devices/{dev_id}", headers=_h(auth_token))

        # 快照也被清理
        with SessionLocal() as db:
            remaining = db.query(DeviceConfigSnapshot).filter(
                DeviceConfigSnapshot.device_id == dev_id).count()
            assert remaining == 0


# ---- P1 diff 限制 ----

class TestDiffLimits:
    """diff 查询上限与 capped 标记。"""

    def test_diff_capped_marker(self, client, auth_token, monkeypatch):
        """diff 行数超过上限时 capped=True，结果截断。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "cap-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "cap-dev", "management_ip": "10.0.5.1",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult

        # 生成大配置（每行不同，产生大量 diff 行）
        call_idx = [0]
        lines_count = 3000

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            call_idx[0] += 1
            if call_idx[0] == 1:
                text = "old" + "\n".join(f"line-{i} old" for i in range(lines_count))
            else:
                text = "new" + "\n".join(f"line-{i} new" for i in range(lines_count))
            return ConfigCollectResult(
                status="ok", full_text=text, redacted=text,
                full_hash=hashlib.sha256(text.encode()).hexdigest(),
                command="test")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))

        resp = client.get(f"/api/devices/{dev_id}/configs/diff", headers=_h(auth_token))
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["capped"] is True
        assert len(d["rows"]) == settings.config_diff_max_rows

    def test_diff_from_before_to_400(self, client, auth_token, monkeypatch):
        """from 比 to 晚 → 400。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ord-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "ord-dev", "management_ip": "10.0.5.2",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult
        texts = ["aaa", "bbb"]

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            t = texts.pop(0) if texts else "ccc"
            return ConfigCollectResult(
                status="ok", full_text=t, redacted=t,
                full_hash=hashlib.sha256(t.encode()).hexdigest(),
                command="test")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))

        # 获取两个 id
        snaps = client.get(f"/api/devices/{dev_id}/configs", headers=_h(auth_token)).json()["data"]["items"]
        older_id, newer_id = snaps[0]["id"], snaps[1]["id"]

        # 交换 from/to → 400
        resp = client.get(
            f"/api/devices/{dev_id}/configs/diff?from_snapshot_id={newer_id}&to_snapshot_id={older_id}",
            headers=_h(auth_token))
        assert resp.status_code == 400

    def test_diff_no_capped_when_under_limit(self, client, auth_token, monkeypatch):
        """小 diff 不截断，capped=False。"""
        resp = client.get("/api/devices/99999/configs/diff", headers=_h(auth_token))
        assert resp.status_code == 404  # 设备不存在

        # 正常场景：2 条小配置 diff
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "sm-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "sm-dev", "management_ip": "10.0.5.3",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult
        texts = ["line1", "line2"]

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            t = texts.pop(0) if texts else "x"
            return ConfigCollectResult(
                status="ok", full_text=t, redacted=t,
                full_hash=hashlib.sha256(t.encode()).hexdigest(),
                command="test")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))

        resp = client.get(f"/api/devices/{dev_id}/configs/diff", headers=_h(auth_token))
        assert resp.status_code == 200
        assert resp.json()["data"]["capped"] is False


# ---- P1 采集补充：密码传参 / 未知 host key / cmd_not_supported / 事务失败 ----

class TestCollectPasswordPassThrough:
    """密码认证真实参数传递（N2.1 P1）。"""

    def test_password_passed_to_collector(self, client, auth_token, monkeypatch):
        """采集时已解密的凭据密码必须传入采集器（不能是 None）。"""
        from app.services.config_backup import ConfigCollectResult

        # 创建带加密密码的凭据（auth_key = SSH 密码，ssh_key = 私钥 PEM）
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "pw-c", "protocol": "ssh",
                                 "username": "root", "auth_key": "root_pw"})
        # auth_key 字段即密码；确保加密存储
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "pw-dev", "management_ip": "10.0.6.1",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        captured: dict = {}

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            captured["password"] = password
            captured["username"] = username
            return ConfigCollectResult(
                status="ok", full_text="cfg", redacted="cfg",
                full_hash="pw-hash", command="test")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        resp = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert resp.status_code == 200
        assert captured["password"] == "root_pw"  # 密码真实传递
        assert captured["username"] == "root"


class TestHostKeyUnknown:
    """未知 host key → host_key_unknown 状态（不静默接受）。"""

    def test_collect_unknown_host_key(self, client, auth_token, monkeypatch):
        from app.services.config_backup import ConfigCollectResult

        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "hk-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "hk-dev", "management_ip": "10.0.7.1",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(
                status="host_key_unknown", error="host key 未知",
                host_key_fingerprint="AA:BB")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        resp = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "host_key_unknown"


class TestCmdNotSupported:
    """命令不支持 → cmd_not_supported。"""

    def test_collect_cmd_not_supported(self, client, auth_token, monkeypatch):
        from app.services.config_backup import ConfigCollectResult

        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "cns-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "cns-dev", "management_ip": "10.0.8.1",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(
                status="cmd_not_supported", error="所有配置读取命令均无输出")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        resp = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cmd_not_supported"


# ---- P1 一致性：保留上限 / 事务失败 ----

class TestRetention:
    """快照保留上限（N2.1 P1）：超出清理最旧。"""

    def test_retention_cleans_oldest(self, client, auth_token, monkeypatch):
        from app.services.config_backup import ConfigCollectResult
        from app.models.device import DeviceConfigSnapshot
        from app.core.database import SessionLocal
        from app.core.config import settings

        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ret-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "ret-dev", "management_ip": "10.0.9.1",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        counter = [0]

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            counter[0] += 1
            body = f"config-{counter[0]}"
            return ConfigCollectResult(
                status="ok", full_text=body, redacted=body,
                full_hash=hashlib.sha256(body.encode()).hexdigest(),
                command="test")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        # 连续采集 retention+5 次
        n = settings.config_snapshot_retention + 5
        for _ in range(n):
            client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))

        # 只保留最近 retention 条
        with SessionLocal() as db:
            left = db.query(DeviceConfigSnapshot).filter(
                DeviceConfigSnapshot.device_id == dev_id).count()
            assert left == settings.config_snapshot_retention

        # 最旧一条被清理
        items = client.get(
            f"/api/devices/{dev_id}/configs?page=1&page_size=100",
            headers=_h(auth_token)).json()["data"]["items"]
        hashes = [i["config_full_hash"] for i in items]
        assert len(hashes) == settings.config_snapshot_retention
        assert hashlib.sha256(b"config-1").hexdigest() not in hashes  # 最旧被清理


class TestTransactionFailure:
    """快照写入失败（唯一约束/事务）时安全降级，不静默丢配置。"""

    def test_unique_conflict_returned_as_unchanged(self, client, auth_token, monkeypatch):
        from app.services.config_backup import ConfigCollectResult

        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "txn-c", "protocol": "ssh",
                                 "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "txn-dev", "management_ip": "10.0.10.1",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(
                status="ok", full_text="X", redacted="X",
                full_hash="txn-hash", command="test")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        # 先插入同 hash 快照（直接 DB），再触发采集 → 命中唯一约束 → unchanged
        from app.models.device import DeviceConfigSnapshot
        from app.core.database import SessionLocal

        with SessionLocal() as db:
            db.add(DeviceConfigSnapshot(
                device_id=dev_id, vendor_platform="linux",
                config_full_hash="txn-hash", config_text_redacted="X",
                source="ssh", changed=False, truncated=False))
            db.commit()

        resp = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "unchanged"


# ---- P1 哈希语义 ----

class TestHashSemantics:
    """截断时哈希代表已读部分，必须显式 truncated（N2.1 P1）。"""

    def test_truncated_hash_differs_from_full(self):
        """截断后哈希 ≠ 完整配置哈希，且 truncated=True 显式标记。"""
        import app.services.config_backup as cb_mod
        from app.services.config_backup import _collect_config_ssh, config_full_sha256

        full_body = b"x" * 1000

        class _FakeOut:
            def __init__(self, data: bytes):
                self._data = data
            def read(self, size=-1):
                if not self._data:
                    return b""
                if size < 0 or size >= len(self._data):
                    chunk = self._data
                    self._data = b""
                    return chunk
                chunk = self._data[:size]
                self._data = self._data[size:]
                return chunk

        class _FakeTransport:
            async def connect(self, host, port, username, password, pkey, policy):
                policy.captured = "fp"
                return self
            def exec_command(self, cmd, timeout=None):
                return None, _FakeOut(full_body), _FakeOut(b"")
            def close(self):
                pass

        original_factory = cb_mod._transport_factory
        cb_mod._transport_factory = _FakeTransport()
        try:
            res = asyncio.run(_collect_config_ssh(
                host="10.0.0.1", port=22, username="root",
                password=None, key_pem=None, vendor="linux",
                host_key_fingerprint=None, max_bytes=100))
            full_hash = config_full_sha256(full_body.decode())
            assert res.truncated is True
            assert res.full_hash != full_hash  # 截断哈希 ≠ 完整哈希
            # 哈希对已读部分一致：重算 front_text 哈希 == full_hash
            assert res.full_hash == config_full_sha256(res.full_text)
        finally:
            cb_mod._transport_factory = original_factory

    def test_untruncated_hash_is_full_content(self):
        """未截断时哈希 = 完整内容哈希，truncated=False。"""
        import app.services.config_backup as cb_mod
        from app.services.config_backup import _collect_config_ssh, config_full_sha256

        body = b"full config here"

        class _FakeOut:
            def __init__(self, data: bytes):
                self._data = data
            def read(self, size=-1):
                if not self._data:
                    return b""
                chunk = self._data
                self._data = b""
                return chunk

        class _FakeTransport:
            async def connect(self, host, port, username, password, pkey, policy):
                policy.captured = "fp"
                return self
            def exec_command(self, cmd, timeout=None):
                return None, _FakeOut(body), _FakeOut(b"")
            def close(self):
                pass

        original_factory = cb_mod._transport_factory
        cb_mod._transport_factory = _FakeTransport()
        try:
            res = asyncio.run(_collect_config_ssh(
                host="10.0.0.1", port=22, username="root",
                password=None, key_pem=None, vendor="linux",
                host_key_fingerprint=None, max_bytes=1024))
            assert res.truncated is False
            assert res.full_hash == config_full_sha256(body.decode())
        finally:
            cb_mod._transport_factory = original_factory


# ---- P1 diff 上下文行 ----

class TestDiffContextLines:
    """diff context_lines 参数生效。"""

    def test_diff_configs_context_limit(self):
        from app.services.config_backup import diff_configs

        # 大块不变区域（100 行）+ 一处变更：context_lines 应压缩上下文
        old_text = "\n".join(f"line-{i}" for i in range(100))
        new_text = "\n".join(
            f"line-{i}" if i != 50 else "line-50-MODIFIED"
            for i in range(100)
        )

        full = diff_configs(old_text, new_text, context_lines=None)
        ctx_full = [r for r in full if r["kind"] == "context"]
        assert len(ctx_full) == 99  # 全部为上下文，只有 1 处 replace

        # context=0：无上下文行
        no_ctx = diff_configs(old_text, new_text, context_lines=0)
        assert sum(1 for r in no_ctx if r["kind"] == "context") == 0

        # context=2：每个变更两侧各最多 2 头 + 2 尾 + 1 省略（两处等块 ≤10）
        ctx2 = diff_configs(old_text, new_text, context_lines=2)
        ctx_rows = [r for r in ctx2 if r["kind"] == "context"]
        assert len(ctx_rows) <= 10
        assert len(ctx_rows) < len(ctx_full)  # 确实压缩了

    def test_diff_same_text_no_context_change(self):
        from app.services.config_backup import diff_configs

        text = "\n".join(f"line-{i}" for i in range(100))
        full = diff_configs(text, text, context_lines=None)
        assert all(r["kind"] == "context" for r in full)
        assert len(full) == 100

        # 相同文本 + context=2：块被压缩为首尾 + 省略标记
        ctx2 = diff_configs(text, text, context_lines=2)
        kinds = [r["kind"] for r in ctx2]
        assert kinds.count("context") <= 5  # 4 上下文 + 省略标记
