from fastapi.testclient import TestClient


def test_topology_require_token(client: TestClient):
    assert client.get("/api/topology").status_code == 401


def test_topology_nodes_status_and_links(client: TestClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    client.put(
        "/api/assets/1",
        headers=headers,
        json={
            "name": "核心Web",
            "ip": "192.168.10.10",
            "hostname": "web.local",
            "asset_type": "web_service",
            "status": "warning",
        },
    )

    resp = client.get("/api/topology", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert any(node["id"] == "core-network" and node["category"] == "core" for node in data["nodes"])
    asset_node = next(node for node in data["nodes"] if node["id"] == "asset-1")
    assert asset_node["status"] == "warning"
    assert asset_node["category"] == "web_service"
    assert asset_node["color"] == "#f59e0b"
    assert {"source": "core-network", "target": "asset-1"} in data["links"]
