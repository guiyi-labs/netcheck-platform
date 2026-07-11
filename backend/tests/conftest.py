"""测试公共配置。

使用独立的临时 SQLite 文件，避免污染开发库。每个用例前重建表，由 lifespan 演示数据
init_db 写入 admin + 12 条演示资产，保证用例可复现。
"""
import os
import tempfile
from pathlib import Path

# 必须在导入 app 之前设置数据库 URL，使 app.engine 指向测试库
_test_db = Path(tempfile.gettempdir()) / "netcheck_test.db"
for suffix in ("", "-wal", "-shm"):
    _p = str(_test_db) + suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["NETCHECK_DATABASE_URL"] = f"sqlite:///{_test_db.as_posix()}"
os.environ["NETCHECK_REPORTS_DIR"] = str(Path(tempfile.gettempdir()) / "netcheck_reports_test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402


@pytest.fixture()
def client():
    """每个用例独立的干净数据库：重建表 -> lifespan 写入演示数据 -> 用例 -> 清空。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        # 进入上下文触发 lifespan，执行 init_db 写入 admin + 演示资产
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def auth_token(client: TestClient) -> str:
    """登录并返回 token，供需要鉴权的用例复用。"""
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    return resp.json()["data"]["token"]
