"""B4 多用户与角色：管理员用户管理、viewer 只读限制。"""
from fastapi.testclient import TestClient


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def test_users_requires_admin(client: TestClient, auth_token: str, monkeypatch):
    headers = _h(auth_token)
    listing = client.get("/api/users", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] >= 1


def test_create_update_delete_user_flow(client: TestClient, auth_token: str):
    headers = _h(auth_token)
    created = client.post(
        "/api/users",
        headers=headers,
        json={"username": "ops01", "password": "Ops@password1", "role": "operator"},
    )
    assert created.status_code == 201
    user_id = created.json()["data"]["id"]
    assert created.json()["data"]["role"] == "operator"
    assert created.json()["data"]["is_active"] is True

    # 弱密码拒绝
    weak = client.post("/api/users", headers=headers, json={"username": "ops02", "password": "short", "role": "operator"})
    assert weak.status_code == 422

    # 用户名冲突
    dup = client.post("/api/users", headers=headers, json={"username": "ops01", "password": "Ops@password2", "role": "operator"})
    assert dup.status_code == 409

    # 更新角色 + 改密
    updated = client.put(f"/api/users/{user_id}", headers=headers, json={"role": "viewer", "password": "View@password1"})
    assert updated.status_code == 200
    assert updated.json()["data"]["role"] == "viewer"

    # viewer 能登录，但写操作被拒（403）
    viewer_token = _login(client, "ops01", "View@password1")
    viewer_headers = _h(viewer_token)
    denied = client.post("/api/assets", headers=viewer_headers, json={"name": "只读测试", "ip": "10.77.0.1", "asset_type": "server"})
    assert denied.status_code == 403
    read_ok = client.get("/api/assets", headers=viewer_headers)
    assert read_ok.status_code == 200

    # 删除
    deleted = client.delete(f"/api/users/{user_id}", headers=headers)
    assert deleted.status_code == 200
    # 删除后 viewer token 失效
    gone = client.get("/api/assets", headers=viewer_headers)
    assert gone.status_code == 401


def test_cannot_delete_or_disable_self(client: TestClient, auth_token: str):
    headers = _h(auth_token)
    me = client.get("/api/auth/me", headers=headers).json()["data"]
    assert client.delete(f"/api/users/{me['id']}", headers=headers).status_code == 422
    assert client.put(f"/api/users/{me['id']}", headers=headers, json={"is_active": False}).status_code == 422
    assert client.put(f"/api/users/{me['id']}", headers=headers, json={"role": "viewer"}).status_code == 422


def test_inactive_user_cannot_login(client: TestClient, auth_token: str):
    headers = _h(auth_token)
    created = client.post(
        "/api/users",
        headers=headers,
        json={"username": "temp01", "password": "Temp@password1", "role": "operator"},
    ).json()["data"]
    client.put(f"/api/users/{created['id']}", headers=headers, json={"is_active": False})
    resp = client.post("/api/auth/login", json={"username": "temp01", "password": "Temp@password1"})
    assert resp.status_code == 401


def test_operator_can_write_but_not_manage_users(client: TestClient, auth_token: str):
    headers = _h(auth_token)
    client.post("/api/users", headers=headers, json={"username": "op02", "password": "Op@password1", "role": "operator"})
    op_token = _login(client, "op02", "Op@password1")
    op_headers = _h(op_token)
    # 写资产成功
    ok = client.post("/api/assets", headers=op_headers, json={"name": "操作员资产", "ip": "10.78.0.1", "asset_type": "server"})
    assert ok.status_code == 201
    # 管理用户被拒
    assert client.get("/api/users", headers=op_headers).status_code == 403
    assert client.post("/api/users", headers=op_headers, json={"username": "x", "password": "Xxx@password1"}).status_code == 403