"""B5 TLS 证书检测器：有效期判定（有效/即将过期/已过期/无证书/连接失败）。"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.checkers import TlsChecker


class _FakeSocket:
    def __init__(self, cert):
        self.cert = cert

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getpeercert(self):
        return self.cert


class _FakeWrap:
    def __init__(self, cert):
        self.cert = cert

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getpeercert(self):
        return self.cert


def _patch_tls(monkeypatch, cert):
    """将 TlsChecker 的 socket/ssl 调用替换为固定证书。"""

    def fake_create_connection(address, timeout=None):
        return _FakeSocket(None)

    class FakeContext:
        def create_default_context(cls):
            return cls

        def wrap_socket(self, raw, server_hostname=None):
            return _FakeWrap(cert)

    monkeypatch.setattr("app.services.checkers.socket.create_connection", fake_create_connection)
    monkeypatch.setattr("app.services.checkers.ssl", SimpleNamespace(create_default_context=lambda: FakeContext()))


def _cert(not_after: str) -> dict:
    return {"notAfter": not_after, "issuer": (("commonName", "Test CA"),)}


def test_tls_cert_valid(monkeypatch):
    future = (datetime.now() + timedelta(days=365)).strftime("%b %d %H:%M:%S %Y GMT")
    _patch_tls(monkeypatch, _cert(future))
    asset = SimpleNamespace(ip="192.0.2.1", hostname="example.test", ports="443")
    results = TlsChecker().check(asset)
    assert len(results) == 1
    assert results[0].status == "success"
    assert "TLS 证书有效" in results[0].message
    assert "剩余" in results[0].message


def test_tls_cert_expiring_soon(monkeypatch):
    soon = (datetime.now() + timedelta(days=10)).strftime("%b %d %H:%M:%S %Y GMT")
    _patch_tls(monkeypatch, _cert(soon))
    asset = SimpleNamespace(ip="192.0.2.2", hostname=None, ports="443")
    results = TlsChecker().check(asset)
    assert len(results) == 1
    assert results[0].status == "warning"
    assert "即将过期" in results[0].message


def test_tls_cert_expired(monkeypatch):
    past = (datetime.now() - timedelta(days=5)).strftime("%b %d %H:%M:%S %Y GMT")
    _patch_tls(monkeypatch, _cert(past))
    asset = SimpleNamespace(ip="192.0.2.3", hostname=None, ports="443")
    results = TlsChecker().check(asset)
    assert results[0].status == "failed"
    assert "已过期" in results[0].error_message


def test_tls_connection_failure_is_failed(monkeypatch):
    def boom(address, timeout=None):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr("app.services.checkers.socket.create_connection", boom)
    asset = SimpleNamespace(ip="192.0.2.4", hostname=None, ports="443")
    results = TlsChecker().check(asset)
    assert results[0].status == "failed"
    assert "refused" in results[0].error_message


def test_tls_ports_default_to_443(monkeypatch):
    future = (datetime.now() + timedelta(days=100)).strftime("%b %d %H:%M:%S %Y GMT")
    calls: list[tuple] = []

    def fake_create_connection(address, timeout=None):
        calls.append(address)
        return _FakeSocket(None)

    class FakeContext:
        def create_default_context(cls):
            return cls

        def wrap_socket(self, raw, server_hostname=None):
            return _FakeWrap(_cert(future))

    monkeypatch.setattr("app.services.checkers.socket.create_connection", fake_create_connection)
    monkeypatch.setattr("app.services.checkers.ssl", SimpleNamespace(create_default_context=lambda: FakeContext()))
    asset = SimpleNamespace(ip="192.0.2.5", hostname=None, ports="80,8080")
    TlsChecker().check(asset)
    assert calls == [("192.0.2.5", 443)]