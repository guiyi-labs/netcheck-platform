from fastapi.testclient import TestClient


def test_discovery_require_token(client: TestClient):
    assert client.get("/api/discovery/scans").status_code == 401


def test_discovery_scan_import_invalid_and_limit(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}

    monkeypatch.setattr("app.services.discovery.ping_probe", lambda ip: ip == "10.10.10.10")
    monkeypatch.setattr("app.services.discovery.port_probe", lambda ip, ports: [ports[0]] if ip == "10.10.10.10" and ports else [])
    monkeypatch.setattr("app.services.discovery.reverse_hostname", lambda ip: "found.local")

    invalid = client.post("/api/discovery/scans", headers=headers, json={"target_range": "bad-cidr", "scan_mode": "ping"})
    assert invalid.status_code == 422

    too_many = client.post("/api/discovery/scans", headers=headers, json={"target_range": "10.20.0.0/23", "scan_mode": "ping"})
    assert too_many.status_code == 422

    scan = client.post(
        "/api/discovery/scans",
        headers=headers,
        json={"target_range": "10.10.10.10,10.10.10.11", "scan_mode": "ping_port", "ports": "80,443"},
    )
    assert scan.status_code == 201
    scan_data = scan.json()["data"]
    assert scan_data["status"] == "completed"
    assert scan_data["total_targets"] == 2
    assert scan_data["discovered_count"] == 1

    results = client.get(f"/api/discovery/scans/{scan_data['id']}/results", headers=headers).json()["data"]
    assert results["total"] == 1
    result = results["items"][0]
    assert result["ip"] == "10.10.10.10"
    assert result["already_exists"] is False

    imported = client.post(f"/api/discovery/results/{result['id']}/import", headers=headers)
    assert imported.status_code == 200
    asset = imported.json()["data"]
    assert asset["ip"] == "10.10.10.10"
    assert asset["ports"] == "80"

    imported_again = client.post(f"/api/discovery/results/{result['id']}/import", headers=headers)
    assert imported_again.status_code == 200
    assert imported_again.json()["data"]["id"] == asset["id"]
