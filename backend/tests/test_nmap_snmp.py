"""C3 Nmap 增强发现 + C4 SNMP 基础采集：解析逻辑与回落行为（全部 mock 命令）。"""
from types import SimpleNamespace

from app.core.config import settings
from app.services import nmap_discovery, snmp_basic


# ---------- C3: nmap ----------

def _snmap(stdout: str, returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_nmap_ping_sweep_parses_report(monkeypatch):
    monkeypatch.setattr(nmap_discovery, "_nmap_available", lambda: True)
    monkeypatch.setattr(
        nmap_discovery.subprocess,
        "run",
        lambda *a, **k: _snmap(
            "Starting Nmap 7.94\nNmap scan report for 192.168.1.1\nNmap scan report for 192.168.1.5\nNmap done"
        ),
    )
    assert nmap_discovery.nmap_ping_sweep(["192.168.1.0/30"]) == {"192.168.1.1", "192.168.1.5"}


def test_nmap_ping_sweep_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(nmap_discovery, "_nmap_available", lambda: False)
    assert nmap_discovery.nmap_ping_sweep(["10.0.0.1"]) is None


def test_nmap_ping_sweep_returns_empty_on_failure(monkeypatch):
    monkeypatch.setattr(nmap_discovery, "_nmap_available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("nmap exploded")

    monkeypatch.setattr(nmap_discovery.subprocess, "run", boom)
    assert nmap_discovery.nmap_ping_sweep(["10.0.0.1"]) is None


def test_nmap_port_scan_parses_open(monkeypatch):
    monkeypatch.setattr(nmap_discovery, "_nmap_available", lambda: True)
    monkeypatch.setattr(
        nmap_discovery.subprocess,
        "run",
        lambda *a, **k: _snmap(
            "22/tcp open  ssh\n80/tcp open  http\n443/tcp closed https"
        ),
    )
    assert nmap_discovery.nmap_port_scan("192.168.1.1", [22, 80, 443]) == [22, 80]


def test_discovery_falls_back_to_ping_probe_when_nmap_missing(client, auth_token, monkeypatch):
    """nmap 不可用时 run_discovery_scan 回退 ping_probe（不报错）。"""
    from app.services import discovery as discovery_svc

    monkeypatch.setattr(nmap_discovery, "_nmap_available", lambda: False)
    monkeypatch.setattr(discovery_svc, "ping_probe", lambda ip: ip == "10.0.0.1")
    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = client.post(
        "/api/discovery/scans",
        headers=headers,
        json={"target_range": "10.0.0.1,10.0.0.2", "scan_mode": "ping"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert data["discovered_count"] == 1


# ---------- C4: SNMP ----------

def _ssnmp(stdout: str, returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_snmp_get_parses_value(monkeypatch):
    monkeypatch.setattr(snmp_basic, "_snmp_tools_available", lambda: True)
    monkeypatch.setattr(
        snmp_basic.subprocess,
        "run",
        lambda *a, **k: _ssnmp("SNMPv2-MIB::sysDescr.0 = STRING: Linux host 5.15"),
    )
    value = snmp_basic.snmp_get("192.168.1.1", snmp_basic.OID_SYSDESCR)
    assert value == "Linux host 5.15"


def test_snmp_get_returns_none_when_tools_missing(monkeypatch):
    monkeypatch.setattr(snmp_basic, "_snmp_tools_available", lambda: False)
    assert snmp_basic.snmp_get("1.1.1.1", snmp_basic.OID_SYSDESCR) is None


def test_snmp_get_returns_none_on_timeout(monkeypatch):
    monkeypatch.setattr(snmp_basic, "_snmp_tools_available", lambda: True)

    def boom(*a, **k):
        return _ssnmp("", returncode=1)

    monkeypatch.setattr(snmp_basic.subprocess, "run", boom)
    assert snmp_basic.snmp_get("192.168.1.1", snmp_basic.OID_SYSDESCR) is None


def test_snmp_walk_parses_rows(monkeypatch):
    monkeypatch.setattr(snmp_basic, "_snmp_tools_available", lambda: True)
    monkeypatch.setattr(
        snmp_basic.subprocess,
        "run",
        lambda *a, **k: _ssnmp(
            "IF-MIB::ifDescr.1 = STRING: eth0\nIF-MIB::ifDescr.2 = STRING: eth1"
        ),
    )
    rows = snmp_basic.snmp_walk("192.168.1.1", snmp_basic.OID_IFDESCR)
    assert rows == [("IF-MIB::ifDescr.1", "eth0"), ("IF-MIB::ifDescr.2", "eth1")]


def test_collect_device_basics_empty_when_no_tools(monkeypatch):
    monkeypatch.setattr(snmp_basic, "_snmp_tools_available", lambda: False)
    assert snmp_basic.collect_device_basics("192.168.1.1") is None