"""C2 Traceroute 诊断：输出解析（Linux/BSD 两种格式）+ 接口鉴权。"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services.traceroute import run_traceroute

BSD_OUTPUT = """traceroute to 10.0.0.1 (10.0.0.1), 30 hops max, 60 byte packets
 1  gateway (192.168.1.1)  1.237 ms  1.004 ms  1.135 ms
 2  10.0.0.1 (10.0.0.1)  0.812 ms  0.730 ms  0.891 ms
"""

LINUX_OUTPUT = """traceroute to 8.8.8.8 (8.8.8.8), 15 hops max, 60 byte packets
 1  192.168.1.1  1.237 ms
 2  * * *
 3  8.8.8.8  12.3 ms
"""

TIMEOUT_OUTPUT = """traceroute to 10.99.99.99 (10.99.99.99), 15 hops max, 60 byte packets
 1  192.168.1.1  1.1 ms
 2  * * *
 3  * * *
"""


def _fake_run(stdout: str, returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_parse_bsd_format(monkeypatch):
    monkeypatch.setattr("app.services.traceroute.subprocess.run", lambda *a, **k: _fake_run(BSD_OUTPUT))
    data = run_traceroute("10.0.0.1")
    assert data["status"] == "completed"
    assert len(data["hops"]) == 2
    hop1 = data["hops"][0]
    assert hop1["hop"] == 1
    assert hop1["host"] == "gateway"
    assert hop1["ip"] == "192.168.1.1"
    assert hop1["rtts"][0] == 1.237


def test_parse_linux_format_with_timeout(monkeypatch):
    monkeypatch.setattr("app.services.traceroute.subprocess.run", lambda *a, **k: _fake_run(LINUX_OUTPUT))
    data = run_traceroute("8.8.8.8")
    assert data["status"] == "completed"
    hops = data["hops"]
    assert hops[1]["ip"] == ""
    assert all(rtt is None for rtt in hops[1]["rtts"])
    assert hops[2]["ip"] == "8.8.8.8"


def test_timeout_no_destination(monkeypatch):
    monkeypatch.setattr("app.services.traceroute.subprocess.run", lambda *a, **k: _fake_run(TIMEOUT_OUTPUT))
    data = run_traceroute("10.99.99.99")
    assert data["status"] == "timeout"
    assert data["error"] is not None


def test_failed_execution(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("traceroute not found")

    monkeypatch.setattr("app.services.traceroute.subprocess.run", boom)
    data = run_traceroute("10.0.0.1")
    assert data["status"] == "failed"
    assert "traceroute 执行失败" in data["error"]


def test_empty_target():
    data = run_traceroute("")
    assert data["status"] == "failed"


def test_endpoint_requires_auth(client: TestClient):
    assert client.post("/api/diagnostics/traceroute", params={"target": "10.0.0.1"}).status_code == 401


def test_endpoint_runs_traceroute(client: TestClient, auth_token: str, monkeypatch):
    monkeypatch.setattr(
        "app.services.traceroute.subprocess.run",
        lambda *a, **k: _fake_run(BSD_OUTPUT),
    )
    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = client.post("/api/diagnostics/traceroute", params={"target": "10.0.0.1", "max_hops": 5}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert len(data["hops"]) == 2