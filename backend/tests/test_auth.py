from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.ratelimit import reset_all_failures
from app.core.security import utcnow
from app.models.user import User


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


def test_login_sets_token_expiry(client: TestClient):
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None
        assert user.api_token_expires_at is not None
    finally:
        db.close()


def test_expired_token_rejected(client: TestClient):
    # 直接构造一个已过期的 token 记录
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        user.api_token = "expired-token-123"
        user.api_token_expires_at = utcnow() - timedelta(hours=2)
        db.commit()
    finally:
        db.close()
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer expired-token-123"})
    assert resp.status_code == 401


def test_change_password_policy_and_relogin(client: TestClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    # 新密码太短
    short = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "admin123", "new_password": "123"},
    )
    assert short.status_code == 422
    # 原密码错误
    wrong = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "bad", "new_password": "newpass123"},
    )
    assert wrong.status_code == 400
    # 正确改密：旧 token 失效，新密码可登录
    ok = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "admin123", "new_password": "newpass123"},
    )
    assert ok.status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    relogin = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "newpass123"},
    )
    assert relogin.status_code == 200


def test_login_rate_limit_locks_after_max_attempts(client: TestClient, monkeypatch):
    reset_all_failures()
    monkeypatch.setattr("app.core.ratelimit.settings.login_max_attempts", 3)
    for _ in range(3):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401
    locked = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert locked.status_code == 429
    assert "锁定" in locked.json()["detail"]
    # 锁定期间即使密码正确也拒绝
    denied = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert denied.status_code == 429
    reset_all_failures()