"""N1 SSH 只读采集：host key 策略、命令 allowlist、失败分类、脱敏、解析。"""
from datetime import datetime, timedelta

import pytest

from app.models.device import SSH_READONLY_COMMANDS, SSH_VENDOR_ADAPTERS
from app.services.ssh_collector import (
    HostKeyPolicy,
    _redact_banner,
    _truncated,
    collect_ssh,
)
from app.services.interface_rate import (
    compute_rate,
    classify_interface,
)


# ---------- 厂商/命令 allowlist ----------

def test_vendor_adapters_allowlist():
    assert "linux" in SSH_VENDOR_ADAPTERS
    assert "cisco_ios" in SSH_VENDOR_ADAPTERS
    assert "generic" in SSH_VENDOR_ADAPTERS


def test_readonly_commands_allowlist_no_write_commands():
    for vendor, cmds in SSH_READONLY_COMMANDS.items():
        for cmd in cmds:
            assert "show" in cmd or "cat" in cmd or "uname" in cmd or "hostname" in cmd \
                or cmd.startswith("ip ") or "uptime" in cmd or "free" in cmd or "df" in cmd
            assert not any(w in cmd for w in ("configure", "write", "copy run", "reload"))


def test_unsupported_vendor_rejected():
    import asyncio

    result = asyncio.run(collect_ssh("192.168.1.1", 22, "monitor", vendor="cisco_bad"))
    assert result.status == "error"
    assert "不支持的厂商适配器" in (result.error or "")


# ---------- host key 策略 ----------

class _FakeKey:
    """模拟 paramiko key：get_fingerprint() 返回原始字节（如真实实现）。"""

    def __init__(self, hex_fp):
        self._hex = hex_fp

    def get_fingerprint(self):
        return bytes.fromhex(self._hex)


def test_missing_host_key_without_expected_raises():
    import paramiko

    policy = HostKeyPolicy(None)
    with pytest.raises(paramiko.SSHException):
        policy.missing_host_key(None, "10.0.0.1", _FakeKey("aabbccdd1122"))
    assert policy.captured == "aabbccdd1122"


def test_host_key_match_passes():
    policy = HostKeyPolicy("aabbccdd1122")
    policy.missing_host_key(None, "10.0.0.1", _FakeKey("aabbccdd1122"))  # 不抛
    assert policy.captured == "aabbccdd1122"


def test_host_key_mismatch_raises():
    import paramiko

    policy = HostKeyPolicy("expected-fp")
    with pytest.raises(paramiko.SSHException):
        policy.missing_host_key(None, "10.0.0.1", _FakeKey("ffeeddccbbaa"))


# ---------- 脱敏 ----------

def test_redact_banner_strips_password_lines():
    out = _redact_banner(
        "Last login: Thu Jan 1\nPassword: secret123\nuser@host:~$ uname -a"
    )
    assert "secret123" not in out
    assert "[PROMPT]" in out


def test_truncated_limits_output(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ssh_max_output_bytes", 10)
    assert _truncated("x" * 100) == "x" * 10 + "[TRUNCATED]"


# ---------- 采集流程（mock transport） ----------

def _patch_factory(monkeypatch, connect_fn):
    """把工厂接上 fake connect（普通函数，非绑定方法）。"""
    monkeypatch.setattr(
        "app.services.ssh_collector._transport_factory",
        type("F", (), {"connect": staticmethod(connect_fn)})(),
    )


def _run(host, vendor, password=None, key_pem=None, fp=None):
    import asyncio

    return asyncio.run(
        collect_ssh(
            host, 22, "monitor", password=password, key_pem=key_pem,
            vendor=vendor, host_key_fingerprint=fp,
        )
    )


class _FakeExecClient:
    """模拟 paramiko SSHClient：exec_command 返回 (stdin, stdout, stderr)。"""

    def __init__(self, outputs: dict, fail_cmd: str | None = None):
        self.outputs = outputs
        self.fail_cmd = fail_cmd
        self.executed = []

    def exec_command(self, cmd, timeout=None):
        self.executed.append(cmd)

        class _Out:
            def __init__(self, text):
                self.text = text

            def read(self):
                return self.text.encode()

        return None if cmd == self.fail_cmd else None, \
            _Out(self.outputs.get(cmd, "")), None

    def close(self):
        pass


def _make_ok_client():
    return _FakeExecClient({
        "hostname -f": "edge01\n",
        "uname -a": "Linux demo 5.15.0-91-generic #102-Ubuntu SMP\n",
        "ip -o link show": "1: lo: <LOOPBACK> mtu 65536\n",
        "ip route show": "default via 10.0.0.1 dev eth0\n",
        "cat /etc/hosts": "127.0.0.1 localhost\n",
        "uptime": "up 5 days, 3:22, 2 users\n",
        "free -h": "              total        used        free\nMem:           100Mi       20Mi      80Mi\n",
        "df -h": "/dev/sda1 50G 10G 40G\n",
    })


def test_collect_ssh_success_with_mock_transport(monkeypatch):
    """正常场景：mock client 返回命令输出。"""
    client = _make_ok_client()

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "known-fp"
        return client

    _patch_factory(monkeypatch, fake_connect)

    result = _run("10.0.0.1", "linux", password="pass")
    assert result.status == "ok"
    assert result.facts.get("hostname") == "edge01"
    assert "uname -a" in result.raw_outputs
    assert len(result.raw_outputs) <= 5  # 有界命令数


def test_collect_ssh_auth_failed(monkeypatch):
    import paramiko

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        raise paramiko.AuthenticationException("bad credentials")

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.0.1", "linux", password="wrong")
    assert result.status == "auth_failed"


def test_collect_ssh_host_key_unknown(monkeypatch):
    import paramiko

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "unknown-fp"
        raise paramiko.SSHException("first connect, host key unknown")

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.0.1", "linux", password="pass")
    assert result.status == "host_key_unknown"
    assert result.host_key_fingerprint == "unknown-fp"


def test_collect_ssh_host_key_mismatch(monkeypatch):
    import paramiko

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "actual-fp"
        raise paramiko.SSHException("host key mismatch: expected-fp actual-fp")

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.0.1", "linux", password="pass", fp="expected-fp")
    assert result.status == "host_key_mismatch"


def test_collect_ssh_conn_refused(monkeypatch):
    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        raise ConnectionRefusedError()

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.0.1", "linux", password="pass")
    assert result.status == "conn_refused"


def test_collect_ssh_timeout(monkeypatch):
    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        raise TimeoutError()

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.0.1", "linux", password="pass")
    assert result.status == "timeout"


# ---------- 接口速率 ----------

def test_rate_normal():
    prev = datetime(2025, 1, 1)
    curr = prev + timedelta(seconds=10)
    assert compute_rate(0, 100, prev, curr) == 80.0


def test_rate_counter_wrap():
    prev = datetime(2025, 1, 1)
    curr = prev + timedelta(seconds=10)
    # wrap: prev=2^64-200, curr=100 → 修正后增量为 100+200=300 → 300B/10s=30B/s=240bps
    rate = compute_rate(2**64 - 200, 100, prev, curr)
    assert rate == 240.0


def test_rate_restart_detected():
    prev = datetime(2025, 1, 1)
    curr = prev + timedelta(seconds=10)
    rate = compute_rate(10**12, 1000, prev, curr)
    assert rate is None


def test_rate_missing_sample():
    prev = datetime(2025, 1, 1)
    curr = prev + timedelta(seconds=10)
    assert compute_rate(None, 100, prev, curr) is None
    assert compute_rate(0, None, prev, curr) is None
    assert compute_rate(0, 100, None, curr) is None


def test_rate_no_elapsed():
    now = datetime(2025, 1, 1)
    assert compute_rate(0, 100, now, now) is None
    assert compute_rate(0, 100, now + timedelta(seconds=1), now) is None


def test_interface_classify():
    assert classify_interface(1, 1) == "ok"
    assert classify_interface(1, 2) == "down"
    assert classify_interface(2, 1) == "down"
    assert classify_interface(None, None) == "unknown"
    assert classify_interface(None, 1) == "unknown"


def test_collect_ssh_command_unsupported_falls_through(monkeypatch):
    """个别命令不可用：不回滚整个采集，其他命令继续。"""
    client = _make_ok_client()
    client.fail_cmd = "uptime"

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "known-fp"
        return client

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.0.1", "linux", password="pass")
    assert result.status == "ok"
    assert result.facts.get("hostname") == "edge01"