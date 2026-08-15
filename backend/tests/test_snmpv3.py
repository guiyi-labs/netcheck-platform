"""N1 SNMPv3 采集：OID allowlist、算法映射、错误分类、接口解析、上限。"""
import pytest

from app.core.config import settings
from app.models.device import OID_ALLOWLIST
from app.services.snmpv3_collector import (
    SnmpResult,
    _oid_in_allowlist,
    _safe_counter,
    classify_error,
    collect_snmpv3,
    run_snmpv3_sync,
)


# ---------- OID allowlist ----------

def test_oid_allowlist_contains_sys_and_if():
    assert "1.3.6.1.2.1.1.5.0" in OID_ALLOWLIST["sys"]  # sysName
    assert "1.3.6.1.2.1.2.2.1.10" in OID_ALLOWLIST["if"]  # ifInOctets
    assert "1.3.6.1.2.1.2.2.1.16" in OID_ALLOWLIST["if"]  # ifOutOctets


def test_oid_in_allowlist_positive():
    assert _oid_in_allowlist("1.3.6.1.2.1.1.5.0")
    assert _oid_in_allowlist("1.3.6.1.2.1.2.2.1.10")


def test_oid_in_allowlist_rejects_arbitrary():
    assert not _oid_in_allowlist("1.3.6.1.4.1.9999.1.1")  # 私有 MIB
    assert not _oid_in_allowlist("1.3.6.1.2.1.69.1.1")   # LLDP-MIB 不在第一阶段


# ---------- 错误分类 ----------

def test_classify_timeout():
    from pysnmp.proto.errind import RequestTimedOut

    assert classify_error(RequestTimedOut(), 0) == "timeout"


def test_classify_auth_failed():
    from pysnmp.proto.errind import AuthenticationError

    assert classify_error(AuthenticationError(), 0) == "auth_failed"


def test_classify_priv_failed():
    """隐私密钥错误 → priv_failed（如 pysnmp 返回含 priv 的错误）。"""

    class PrivError:
        """模拟 pysnmp 的 PrivError（类名含 priv 即可识别）。"""

    assert classify_error(PrivError(), 0) == "priv_failed"


def test_classify_ok():
    assert classify_error(None, 0) == "ok"


def test_classify_unknown_returns_error():
    assert classify_error("SomeOtherError", 0) == "error"


# ---------- 数值解析 ----------

def test_safe_counter():
    assert _safe_counter("12345") == 12345
    assert _safe_counter("") is None
    assert _safe_counter(None) is None
    assert _safe_counter("not-a-number") is None


# ---------- 采集主流程（mock transport） ----------

class FakeObj:
    def __init__(self, value, name="OctetString"):
        self._v = value
        self.__name = name

    def prettyPrint(self):
        return str(self._v)


def test_snmpv3_collect_returns_ok_with_facts(monkeypatch):
    """正常场景：sys* 有值 + 接口计数器。"""
    monkeypatch.setattr("app.services.snmpv3_collector._get", _fake_get)
    monkeypatch.setattr("app.services.snmpv3_collector._walk", _fake_walk)

    result = run_snmpv3_sync(
        "192.168.1.1", "monitor", "authkey123", "privkey123",
        "SHA-256", "AES-128",
    )
    assert result.status == "ok"
    assert result.facts.get("sys_name") == "router1"
    assert len(result.interfaces) >= 2


async def _fake_get(transport, user, oid):
    responses = {
        "1.3.6.1.2.1.1.1.0": "Linux host 5.15",
        "1.3.6.1.2.1.1.3.0": "123456",
        "1.3.6.1.2.1.1.5.0": "router1",
        "1.3.6.1.2.1.1.4.0": "",
        "1.3.6.1.2.1.1.6.0": "",
    }
    return None, 0, [(None, FakeObj(responses.get(oid, "")))]


async def _fake_walk(transport, user, oid):
    """返回预置接口表 walk 结果。"""
    tables = {
        "1.3.6.1.2.1.2.2.1.2": [("1.3.6.1.2.1.2.2.1.2.1", "eth0"),
                                ("1.3.6.1.2.1.2.2.1.2.2", "eth1")],
        "1.3.6.1.2.1.2.2.1.3": [("1.3.6.1.2.1.2.2.1.3.1", "6"),
                                ("1.3.6.1.2.1.2.2.1.3.2", "6")],
        "1.3.6.1.2.1.2.2.1.5": [("1.3.6.1.2.1.2.2.1.5.1", "1000000000"),
                                ("1.3.6.1.2.1.2.2.1.5.2", "1000000000")],
        "1.3.6.1.2.1.2.2.1.7": [("1.3.6.1.2.1.2.2.1.7.1", "1"),
                                ("1.3.6.1.2.1.2.2.1.7.2", "1")],
        "1.3.6.1.2.1.2.2.1.8": [("1.3.6.1.2.1.2.2.1.8.1", "1"),
                                ("1.3.6.1.2.1.2.2.1.8.2", "2")],
        "1.3.6.1.2.1.2.2.1.10": [("1.3.6.1.2.1.2.2.1.10.1", "1000"),
                                 ("1.3.6.1.2.1.2.2.1.10.2", "2000")],
        "1.3.6.1.2.1.2.2.1.16": [("1.3.6.1.2.1.2.2.1.16.1", "3000"),
                                 ("1.3.6.1.2.1.2.2.1.16.2", "4000")],
    }
    return tables.get(oid, []), None, []


def test_snmpv3_auth_failed_sets_status(monkeypatch):
    """认证失败：status=auth_failed。"""

    class AuthenticationError:
        """模拟 pysnmp 的 AuthenticationError（类名即识别依据）。"""

    async def fake_get(transport, user, oid):
        return AuthenticationError(), 0, []

    async def fake_walk(transport, user, oid):
        return [], None, []

    monkeypatch.setattr("app.services.snmpv3_collector._get", fake_get)
    monkeypatch.setattr("app.services.snmpv3_collector._walk", fake_walk)

    result = run_snmpv3_sync(
        "192.168.1.1", "monitor", "wrongkey", "wrongkey",
    )
    assert result.status == "auth_failed"


def test_snmpv3_missing_pysnmp_returns_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.snmpv3_collector._PYSNMP_AVAILABLE", False
    )
    result = run_snmpv3_sync("192.168.1.1", "u", "k", "k", )
    assert result.status == "error"


def test_snmpv3_partial_oid_unsupported_is_graceful(monkeypatch):
    """部分 OID 不支持（NoSuchObject）不崩溃，进入 unknown。"""

    class NoSuchObject:
        """模拟 pysnmp 的 NoSuchObject（类名即识别依据）。"""

    async def fake_get(transport, user, oid):
        return None, 0, [(None, NoSuchObject())]

    async def fake_walk(transport, user, oid):
        return [], None, []

    monkeypatch.setattr("app.services.snmpv3_collector._get", fake_get)
    monkeypatch.setattr("app.services.snmpv3_collector._walk", fake_walk)

    result = run_snmpv3_sync("192.168.1.1", "u", "k", "k")
    assert result.status == "ok"  # 不崩溃
    assert result.facts == {}

# ---------- N3 真实设备发现的 USM 认证异常分类 ----------

def test_classify_wrong_digest_auth_failed():
    """真实设备：认证密钥错误 → WrongDigest（N3 实测发现）。"""
    from pysnmp.proto.errind import WrongDigest

    assert classify_error(WrongDigest(), 0) == "auth_failed"


def test_classify_unknown_user_auth_failed():
    """真实设备：用户不存在 → UnknownUserName（N3 实测发现）。"""
    from pysnmp.proto.errind import UnknownUserName

    assert classify_error(UnknownUserName(), 0) == "auth_failed"


def test_classify_not_in_time_window_auth_failed():
    """时钟偏差 → NotInTimeWindow（N3 常见）。"""
    from pysnmp.proto.errind import NotInTimeWindow

    assert classify_error(NotInTimeWindow(), 0) == "auth_failed"


def test_classify_unknown_engine_id_auth_failed():
    from pysnmp.proto.errind import UnknownEngineID

    assert classify_error(UnknownEngineID(), 0) == "auth_failed"
