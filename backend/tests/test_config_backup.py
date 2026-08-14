"""N2 配置备份与差异测试：脱敏、哈希去重、diff、审计日志、失败不落库。"""
import asyncio
import hashlib
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.models.device import DeviceConfigSnapshot


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---- config_backup 服务内部单元测试 ----

class TestRedactSecretValue:
    """脱敏行级测试：只遮蔽密钥值，保留结构。"""

    def test_enable_secret(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("enable secret 5 1234abcdX")
        assert out == "enable secret 5 ********"
        assert "1234abcdX" not in out

    def test_username_password(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("username admin password 0 plaintext")
        assert out == "username admin password 0 ********"
        assert "plaintext" not in out

    def test_snmp_community(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("snmp-server community public RO")
        assert "public" not in out
        assert "snmp-server community" in out

    def test_access_key(self):
        from app.services.config_backup import redact_secret_value

        out = redact_secret_value("ip access-key abcXYZ")
        assert "abcXYZ" not in out

    def test_non_secret_line_unchanged(self):
        from app.services.config_backup import redact_secret_value

        line = "interface GigabitEthernet0/1"
        assert redact_secret_value(line) == line
        line2 = " ip address 10.0.0.1 255.255.255.0"
        assert redact_secret_value(line2) == line2

    def test_empty_line(self):
        from app.services.config_backup import redact_secret_value

        assert redact_secret_value("") == ""
        # 空白行保持原样（redact_config 会在整份级折叠空行）
        assert redact_secret_value("   ") == "   "


class TestRedactConfig:
    """逐行脱敏整份配置：折叠空行、密钥行遮蔽。"""

    def test_full_redaction(self):
        from app.services.config_backup import redact_config

        text = "interface Eth0\nip address 10.0.0.1\nenable secret 5 abc123\n"
        out = redact_config(text)
        assert "abc123" not in out
        assert "interface Eth0" in out
        assert "ip address 10.0.0.1" in out
        # 空行被折叠
        assert out.count("\n") == 2  # 3 lines minus 0 blank = 3 lines (no trailing \n in join)


class TestConfigFullSha256:
    def test_deterministic(self):
        from app.services.config_backup import config_full_sha256

        assert config_full_sha256("x") == config_full_sha256("x")

    def test_different_inputs(self):
        from app.services.config_backup import config_full_sha256

        assert config_full_sha256("x") != config_full_sha256("y")

    def test_hex_length(self):
        from app.services.config_backup import config_full_sha256

        h = config_full_sha256("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestDiffConfigs:
    """行级 diff 验证：新增/删除/修改/上下文/无变化。"""

    def test_no_change(self):
        from app.services.config_backup import diff_configs

        rows = diff_configs("A\nB\nC", "A\nB\nC")
        assert [r["kind"] for r in rows] == ["context", "context", "context"]

    def test_add_line(self):
        from app.services.config_backup import diff_configs

        rows = diff_configs("A\nC", "A\nB\nC")
        kinds = [r["kind"] for r in rows]
        assert kinds == ["context", "add", "context"]
        assert rows[1]["text"] == "B"

    def test_del_line(self):
        from app.services.config_backup import diff_configs

        rows = diff_configs("A\nB\nC", "A\nC")
        kinds = [r["kind"] for r in rows]
        assert "del" in kinds
        del_row = [r for r in rows if r["kind"] == "del"][0]
        assert del_row["text"] == "B"

    def test_replace_line(self):
        from app.services.config_backup import diff_configs

        rows = diff_configs("A\nold\nC", "A\nnew\nC")
        kinds = [r["kind"] for r in rows]
        assert kinds == ["context", "del", "add", "context"]
        assert rows[1]["text"] == "old"
        assert rows[2]["text"] == "new"

    def test_line_numbers(self):
        from app.services.config_backup import diff_configs

        rows = diff_configs("A\nB", "A\nB2\nC")
        # B is deleted (old_line_no=2), B2/C are added
        dels = [r for r in rows if r["kind"] == "del"]
        adds = [r for r in rows if r["kind"] == "add"]
        assert len(dels) == 1 and dels[0]["old_line_no"] == 2
        assert len(adds) == 2 and adds[0]["new_line_no"] == 2

    def test_format_diff_text(self):
        from app.services.config_backup import format_diff_text

        rows = [{"kind": "context", "old_line_no": 1, "new_line_no": 1, "text": "A"},
                {"kind": "del", "old_line_no": 2, "new_line_no": None, "text": "old"},
                {"kind": "add", "old_line_no": None, "new_line_no": 2, "text": "new"},
                {"kind": "context", "old_line_no": 3, "new_line_no": 3, "text": "C"}]
        text = format_diff_text(rows)
        lines = text.split("\n")
        assert lines[0] == " A"
        assert lines[1] == "-old"
        assert lines[2] == "+new"
        assert lines[3] == " C"


# ---- API 集成测试（mock SSH 采集） ----

class TestConfigBackupAPI:
    """通过 FastAPI TestClient 测试 /configs 系列端点。"""

    def test_trigger_config_collect_ok(self, client, auth_token, monkeypatch):
        """配置采集成功：产生新快照，审计日志写入。"""
        # 创建设备（绑定 ssh_config_id）
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ssh-c", "protocol": "ssh", "username": "admin",
                                 "ssh_key": "FAKE_KEY"})
        cred_id = cred.json()["data"]["id"]
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "dev-cfg", "management_ip": "10.0.1.1",
                                "vendor_platform": "linux", "ssh_config_id": cred_id})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(
                status="ok",
                full_text="hostname test-host\ninterface eth0\nenable secret 5 abcXYZ\n",
                redacted="hostname test-host\ninterface eth0\nenable secret 5 ********",
                full_hash=hashlib.sha256(b"full").hexdigest(),
                command="cat /etc/hosts",
                host_key_fingerprint="aabbccdd",
            )

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        resp = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "ok"
        assert body["data"]["changed"] is False  # 首份快照不标记 changed
        snap_id = body["data"]["snapshot_id"]

        # 再次采集 → unchanged（同 hash）
        resp2 = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert resp2.json()["data"]["status"] == "unchanged"

        # 列表确认只有 1 条
        resp3 = client.get(f"/api/devices/{dev_id}/configs", headers=_h(auth_token))
        items = resp3.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["id"] == snap_id

    def test_trigger_config_collect_changed(self, client, auth_token, monkeypatch):
        """第二次采集内容变化 → changed=True，产生第 2 条快照。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ssh-d", "protocol": "ssh", "username": "admin",
                                 "ssh_key": "KEY"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "dev-chg", "management_ip": "10.0.1.2",
                                "vendor_platform": "cisco_ios",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        call_count = [0]
        from app.services.config_backup import ConfigCollectResult

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            call_count[0] += 1
            text = "version 15.1\nhostname router-" + str(call_count[0])
            return ConfigCollectResult(
                status="ok",
                full_text=text,
                redacted=text,  # 无密钥行
                full_hash=hashlib.sha256(text.encode()).hexdigest(),
                command="show running-config",
            )

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        # 第 1 份
        r1 = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert r1.json()["data"]["status"] == "ok"
        assert r1.json()["data"]["changed"] is False  # 首份

        # 第 2 份（内容变化）
        r2 = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert r2.json()["data"]["status"] == "ok"
        assert r2.json()["data"]["changed"] is True

        # 列表 2 条
        items = client.get(f"/api/devices/{dev_id}/configs", headers=_h(auth_token)).json()["data"]["items"]
        assert len(items) == 2

    def test_trigger_config_collect_auth_failed(self, client, auth_token, monkeypatch):
        """SSH 认证失败 → status=auth_failed，不产生快照。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ssh-e", "protocol": "ssh", "username": "admin",
                                 "ssh_key": "KEY"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "dev-authf", "management_ip": "10.0.1.3",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(status="auth_failed", error="SSH 认证失败")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        r = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert r.json()["data"]["status"] == "auth_failed"
        items = client.get(f"/api/devices/{dev_id}/configs", headers=_h(auth_token)).json()["data"]["items"]
        assert len(items) == 0

    def test_trigger_config_collect_timeout(self, client, auth_token, monkeypatch):
        """SSH 超时 → status=timeout，不产生快照。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ssh-t", "protocol": "ssh", "username": "admin",
                                 "ssh_key": "KEY"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "dev-timeout", "management_ip": "10.0.1.4",
                                "vendor_platform": "generic",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(status="timeout", error="SSH 连接超时")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        r = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert r.json()["data"]["status"] == "timeout"
        assert client.get(f"/api/devices/{dev_id}/configs", headers=_h(auth_token)).json()["data"]["total"] == 0

    def test_config_diff_endpoint(self, client, auth_token, monkeypatch):
        """两份快照 diff：返回变更行（add/del/context）。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ssh-diff", "protocol": "ssh", "username": "admin",
                                 "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "dev-diff", "management_ip": "10.0.1.5",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        texts = ["hostname router-1\ninterface eth0\nip addr 1.1.1.1\n",
                 "hostname router-2\ninterface eth0\nip addr 2.2.2.2\nnew-line\n"]
        from app.services.config_backup import ConfigCollectResult

        call_idx = [0]

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            t = texts[call_idx[0]]
            call_idx[0] += 1
            return ConfigCollectResult(
                status="ok", full_text=t, redacted=t,
                full_hash=hashlib.sha256(t.encode()).hexdigest(),
                command="show run")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))

        diff_resp = client.get(f"/api/devices/{dev_id}/configs/diff", headers=_h(auth_token))
        assert diff_resp.status_code == 200
        d = diff_resp.json()["data"]
        assert d["changed"] is True
        assert len(d["rows"]) > 0
        kinds = [r["kind"] for r in d["rows"]]
        assert "del" in kinds
        assert "add" in kinds
        # text 字段有统一 diff 内容
        assert d["text"].startswith(" ") or d["text"].startswith("+") or d["text"].startswith("-")

    def test_config_latest_endpoint(self, client, auth_token, monkeypatch):
        """GET /configs/latest 返回最新快照的脱敏文本。"""
        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ssh-l", "protocol": "ssh", "username": "admin", "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "dev-l", "management_ip": "10.0.1.6",
                                "vendor_platform": "cisco_ios",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(
                status="ok",
                full_text="hostname r1\nenable secret 5 Secret123\n",
                redacted="hostname r1\nenable secret 5 ********",
                full_hash="aaa111", command="show run")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))

        latest = client.get(f"/api/devices/{dev_id}/configs/latest", headers=_h(auth_token))
        assert latest.status_code == 200
        body = latest.json()["data"]
        assert "Secret123" not in body["config_text_redacted"]
        assert "********" in body["config_text_redacted"]
        assert body["vendor_platform"] == "cisco_ios"

    def test_no_ssh_credential_skips(self, client, auth_token):
        """设备无 ssh_config_id → collect 返回 skipped。"""
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "no-ssh", "management_ip": "10.0.1.7",
                                "vendor_platform": "generic"})
        dev_id = dev.json()["data"]["id"]
        r = client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        assert r.json()["data"]["status"] == "skipped"

    def test_audit_log_written(self, client, auth_token, monkeypatch):
        """触发配置备份后审计日志有 device_config_backup 记录。"""
        from app.models.audit import OperationLog

        cred = client.post("/api/devices/credentials", headers=_h(auth_token),
                           json={"name": "ssh-aud", "protocol": "ssh", "username": "admin",
                                 "ssh_key": "K"})
        dev = client.post("/api/devices", headers=_h(auth_token),
                          json={"name": "dev-aud", "management_ip": "10.0.1.8",
                                "vendor_platform": "linux",
                                "ssh_config_id": cred.json()["data"]["id"]})
        dev_id = dev.json()["data"]["id"]

        from app.services.config_backup import ConfigCollectResult

        async def fake_collect(host, port, username, password, key_pem,
                               vendor, host_key_fingerprint, max_bytes):
            return ConfigCollectResult(
                status="ok", full_text="test", redacted="test",
                full_hash="bbb222", command="cat /etc/hosts")

        import app.services.config_backup as cb_mod
        monkeypatch.setattr(cb_mod, "_collect_config_ssh", fake_collect)

        client.post(f"/api/devices/{dev_id}/configs/collect", headers=_h(auth_token))
        with SessionLocal() as db:
            log = (
                db.query(OperationLog)
                .filter(OperationLog.action == "device_config_backup",
                        OperationLog.target_id == dev_id)
                .first()
            )
            assert log is not None
            assert "config_backup" in log.detail
            assert log.username == "admin"


class TestConfigBoundedness:
    """配置采集有界性：max_bytes 截断，超长配置不落库。"""

    def test_max_bytes_truncates_output(self):
        """_collect_config_ssh 对超长输出按 max_bytes 截断。"""
        import app.services.config_backup as cb_mod
        from app.services.config_backup import _collect_config_ssh

        # 注入一个返回长输出的假 transport
        long_output = ("x" * 200)

        class _FakeTransport:
            def __init__(self):
                self.captured_part = ""

            async def connect(self, host, port, username, password, pkey, policy):
                policy.captured = "fp"
                return self

            def exec_command(self, cmd, timeout=None):
                class _Out:
                    def read(self):
                        return long_output.encode()
                return None, _Out(), None

            def close(self):
                pass

        original_factory = cb_mod._transport_factory
        cb_mod._transport_factory = _FakeTransport()
        try:
            res = asyncio.run(_collect_config_ssh(
                host="10.0.0.1", port=22, username="root",
                password=None, key_pem=None, vendor="linux",
                host_key_fingerprint=None, max_bytes=50))
            assert res.status == "ok"
            assert len(res.full_text) == 50  # 被截断到 50 字节
            assert len(res.redacted) <= 50
        finally:
            cb_mod._transport_factory = original_factory

    def test_oversized_max_bytes_would_not_overflow(self):
        """大量数据在读取后截断，不产生天文数字内存（有界）。"""
        import app.services.config_backup as cb_mod
        from app.services.config_backup import _collect_config_ssh

        huge = ("z" * 1_000_000)

        class _FakeTransport:
            async def connect(self, host, port, username, password, pkey, policy):
                policy.captured = "fp"
                return self

            def exec_command(self, cmd, timeout=None):
                class _Out:
                    def read(self):
                        return huge.encode()
                return None, _Out(), None

            def close(self):
                pass

        original_factory = cb_mod._transport_factory
        cb_mod._transport_factory = _FakeTransport()
        try:
            res = asyncio.run(_collect_config_ssh(
                host="10.0.0.1", port=22, username="root",
                password=None, key_pem=None, vendor="linux",
                host_key_fingerprint=None, max_bytes=1024))
            assert res.status == "ok"
            assert len(res.full_text) == 1024
        finally:
            cb_mod._transport_factory = original_factory
