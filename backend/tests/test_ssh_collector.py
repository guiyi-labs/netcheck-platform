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
    assert "h3c_comware" in SSH_VENDOR_ADAPTERS
    assert "generic" in SSH_VENDOR_ADAPTERS


def test_readonly_commands_allowlist_no_write_commands():
    for vendor, cmds in SSH_READONLY_COMMANDS.items():
        for cmd in cmds:
            assert "show" in cmd or "cat" in cmd or "uname" in cmd or "hostname" in cmd \
                or cmd.startswith("ip ") or "uptime" in cmd or "free" in cmd or "df" in cmd \
                or cmd.startswith("display ")
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
        if cmd == self.fail_cmd:
            raise Exception("command not found: " + cmd)

        class _Out:
            def __init__(self, text):
                self.text = text

            def read(self):
                return self.text.encode()

        return None, _Out(self.outputs.get(cmd, "")), None

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
    client.fail_cmd = "cat /etc/hosts"  # 前 5 条命令之一（commands[:5] 有界）

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "known-fp"
        return client

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.0.1", "linux", password="pass")
    assert result.status == "ok"  # hostname -f 成功，cat 失败但不阻断
    assert result.facts.get("hostname") == "edge01"
    assert result.command_errors.get("cat /etc/hosts") == "cmd_not_supported"  # 被拒绝命令标记


def test_collect_ssh_all_commands_unsupported_sets_status(monkeypatch):
    """所有命令都返回 command not found → status=cmd_not_supported。"""

    class _FakeClient:
        def exec_command(self, cmd, timeout=None):
            raise Exception("command not found: " + cmd)

        def close(self):
            pass

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "fp"
        return _FakeClient()

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.0.1", "linux", password="pass")
    assert result.status == "cmd_not_supported"
    assert all(v == "cmd_not_supported" for v in result.command_errors.values())


def test_collect_ssh_parse_failed_detected(monkeypatch):
    """解析异常 → command_errors 记录 parse_failed，状态为 parse_failed。"""

    class _FakeClient:
        def exec_command(self, cmd, timeout=None):
            class _Out:
                def read(self):
                    return b"unexpected binary\n"

            return None, _Out(), None

        def close(self):
            pass

    # 注册一个会抛异常的 parser
    def bad_parser(cmd, output):
        raise ValueError("解析失败")

    from app.services import ssh_collector

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "fp"
        return _FakeClient()

    # 替换 PARSERS 里 linux 的 parser
    original = ssh_collector.PARSERS.get("linux", {}).get("parser", lambda c, o: {})
    ssh_collector.PARSERS["linux"] = ssh_collector.PARSERS.get("linux", {})
    ssh_collector.PARSERS["linux"]["parser"] = bad_parser

    try:
        _patch_factory(monkeypatch, fake_connect)
        result = _run("10.0.0.1", "linux", password="pass")
        assert result.status == "parse_failed"
        assert any(v == "parse_failed" for v in result.command_errors.values())
    finally:
        ssh_collector.PARSERS["linux"]["parser"] = original


# ---------- H3C Comware 适配器（mock 输出验证，无真实 H3C 设备） ----------

def _h3c_client():
    return _FakeExecClient({
        "display version": (
            "H3C Comware Software, Version 7.1.070, Release 1118P02\n"
            "H3C S5560X-30C-EI\n"
            "H3C uptime is 2 weeks, 1 day, 3 hours, 4 minutes\n"
        ),
        "display interface brief": (
            "Brief information on interfaces in route mode:\n"
            "Link: ADM - administratively down; Stby - standby\n"
            "Interface            Link         Speed   Duplex Type PVID Description\n"
            "GE1/0/1              UP           1G      F(a)   A    1    to-core\n"
            "GE1/0/2              DOWN         1G      F(a)   A    1    --\n"
            "Vlan-interface1      UP           10G     F(a)   R    --   --\n"
        ),
        "display ip routing-table": (
            "Destinations : 5        Routes : 5\n"
            "Destination/Mask   Proto   Pre  Cost        NextHop         Interface\n"
            "0.0.0.0/0          Static  60   0           10.0.0.254       Vlan-interface1\n"
            "10.0.0.0/24        Direct  0    0           10.0.0.1         Vlan-interface1\n"
            "192.168.1.0/24     Direct  0    0           192.168.1.1      Vlan-interface1\n"
        ),
        "display clock": (
            "2026-08-15 14:30:00\n"
            "Friday\n"
            "Time Zone : China Standard Time\n"
        ),
    })


def test_h3c_parser_display_version():
    from app.services.ssh_collector import _parse_h3c_comware_output

    facts = _parse_h3c_comware_output("display version", _h3c_client().outputs["display version"])
    assert facts.get("os_version") == "Comware 7.1.070"
    assert facts.get("uptime") == "2 weeks, 1 day, 3 hours, 4 minutes"


def test_h3c_parser_display_interface_brief():
    from app.services.ssh_collector import _parse_h3c_comware_output

    facts = _parse_h3c_comware_output("display interface brief", _h3c_client().outputs["display interface brief"])
    assert facts.get("interfaces_count") == "3"
    assert facts.get("up_count") == "2"
    assert facts.get("down_count") == "1"


def test_h3c_parser_display_ip_routing_table():
    from app.services.ssh_collector import _parse_h3c_comware_output

    facts = _parse_h3c_comware_output("display ip routing-table", _h3c_client().outputs["display ip routing-table"])
    assert facts.get("routes_count") == "3"


def test_h3c_parser_display_clock():
    from app.services.ssh_collector import _parse_h3c_comware_output

    facts = _parse_h3c_comware_output("display clock", _h3c_client().outputs["display clock"])
    assert facts.get("system_time") == "2026-08-15 14:30:00"


def test_collect_ssh_h3c_comware_end_to_end(monkeypatch):
    """H3C 端到端：vendor=h3c_comware 被适配器接受并解析成功。"""
    client = _h3c_client()

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "h3c-fp"
        return client

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.1.1", "h3c_comware", password="pass")
    assert result.status == "ok"
    assert result.facts.get("os_version") == "Comware 7.1.070"
    assert result.facts.get("routes_count") == "3"
    assert all(
        cmd in ("display version", "display interface brief",
                "display ip routing-table", "display clock")
        for cmd in result.raw_outputs
    )

def test_h3c_unknown_command_cmd_not_supported(monkeypatch):
    """Comware 风格未识别命令 → 单命令失败 → 整体 cmd_not_supported（非 ok）。"""
    fake = _FakeExecClient({
        "display version": (
            "H3C Comware Software, Version 7.1.070, Release 1118P02\n"
            "H3C uptime is 2 weeks, 1 day, 3 hours, 4 minutes\n"
        ),
    }, fail_cmd="display version")

    async def fake_connect(host, port, username, password, pkey, host_key_policy):
        host_key_policy.captured = "h3c-fp"
        return fake

    _patch_factory(monkeypatch, fake_connect)
    result = _run("10.0.1.1", "h3c_comware", password="pass")
    assert result.status == "cmd_not_supported"
    assert result.command_errors.get("display version") == "cmd_not_supported"
