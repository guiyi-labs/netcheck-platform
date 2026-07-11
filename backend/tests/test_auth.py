from fastapi.testclient import TestClient


def test_login_success_returns_token(client: TestClient):
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    token = data["data"]["token"]
    assert isinstance(token, str) and len(token) == 64
    assert data["data"]["user"]["username"] == "admin"
    assert data["data"]["user"]["role"] == "admin"


def test_login_wrong_password_rejected(client: TestClient):
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_me_with_token(client: TestClient, auth_token: str):
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "admin"


def test_me_without_token_rejected(client: TestClient):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_logout_invalidates_token(client: TestClient, auth_token: str):
    resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    # 登出后旧 token 失效
    resp2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp2.status_code == 401
