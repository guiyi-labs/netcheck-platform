from fastapi.testclient import TestClient


def test_list_assets_requires_token(client: TestClient):
    resp = client.get("/api/assets")
    assert resp.status_code == 401


def test_list_assets_returns_demo_seed(client: TestClient, auth_token: str):
    resp = client.get("/api/assets", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 12
    assert len(data["items"]) == 12
    assert data["page"] == 1


def test_filter_by_asset_type(client: TestClient, auth_token: str):
    resp = client.get(
        "/api/assets?asset_type=server",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(a["asset_type"] == "server" for a in items)
    # 演示数据中 server 包括：业务服务器01、业务服务器02、堡垒机
    assert len(items) == 3


def test_filter_by_status(client: TestClient, auth_token: str):
    resp = client.get(
        "/api/assets?status=offline",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    # 异常Web服务、业务服务器02、办公终端02
    assert len(items) == 3
    assert all(a["status"] == "offline" for a in items)


def test_meta_types(client: TestClient, auth_token: str):
    resp = client.get(
        "/api/assets/meta/types",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "server" in data["asset_types"]
    assert "online" in data["statuses"]


def test_create_get_update_delete_asset(client: TestClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}

    # 新增
    resp = client.post(
        "/api/assets",
        headers=headers,
        json={
            "name": "测试主机",
            "ip": "192.168.1.100",
            "asset_type": "server",
            "ports": "22",
            "status": "online",
        },
    )
    assert resp.status_code == 201
    asset = resp.json()["data"]
    asset_id = asset["id"]
    assert asset["name"] == "测试主机"

    # 查询详情
    resp = client.get(f"/api/assets/{asset_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["ip"] == "192.168.1.100"

    # 更新
    resp = client.put(
        f"/api/assets/{asset_id}",
        headers=headers,
        json={
            "name": "测试主机-改",
            "ip": "192.168.1.101",
            "asset_type": "server",
            "status": "offline",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "测试主机-改"
    assert resp.json()["data"]["status"] == "offline"

    # 删除
    resp = client.delete(f"/api/assets/{asset_id}", headers=headers)
    assert resp.status_code == 200
    # 再查应 404
    resp = client.get(f"/api/assets/{asset_id}", headers=headers)
    assert resp.status_code == 404


def test_get_nonexistent_asset_returns_404(client: TestClient, auth_token: str):
    resp = client.get(
        "/api/assets/99999",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 404


def test_pagination(client: TestClient, auth_token: str):
    resp = client.get(
        "/api/assets?page=1&page_size=5",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 12
    assert len(data["items"]) == 5

    resp2 = client.get(
        "/api/assets?page=3&page_size=5",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp2.status_code == 200
    # 第三页应剩 2 条
    assert len(resp2.json()["data"]["items"]) == 2
