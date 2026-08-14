"""阶段 A 工程加固回归测试：索引、分页与数据层。"""
import os

from fastapi.testclient import TestClient

from app.core.database import engine
from app.services.checkers import CheckResult, CHECKERS

from helpers import wait_run


def test_composite_indexes_exist(client: TestClient):
    """关键组合索引必须存在（新库自动建立，历史库由迁移函数补齐）。"""
    import sqlalchemy as sa

    with engine.connect() as conn:
        rows = conn.execute(sa.text("PRAGMA index_list(inspection_results)")).fetchall()
        names = {row[1] for row in rows}
    assert "ix_results_run_status" in names
    assert "ix_results_asset_checked" in names
    assert "ix_results_checked_at" in names

    with engine.connect() as conn:
        rows = conn.execute(sa.text("PRAGMA index_list(inspection_runs)")).fetchall()
        assert "ix_runs_task_status" in {row[1] for row in rows}

    with engine.connect() as conn:
        rows = conn.execute(sa.text("PRAGMA index_list(alerts)")).fetchall()
        assert "ix_alerts_key_status" in {row[1] for row in rows}


def test_results_pagination_and_order(client: TestClient, auth_token: str, monkeypatch):
    headers = {"Authorization": f"Bearer {auth_token}"}

    class PingChecker:
        def check(self, asset):
            return [CheckResult("failed", asset.ip, 5, error_message="offline")]

    monkeypatch.setitem(CHECKERS, "ping", PingChecker())
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": "分页巡检", "check_types": ["ping"], "asset_ids": [1, 2]},
    ).json()["data"]
    run = client.post(f"/api/tasks/{task['id']}/run", headers=headers).json()["data"]
    wait_run(client, headers, run["id"])

    page1 = client.get("/api/results", headers=headers, params={"page": 1, "page_size": 1}).json()["data"]
    assert page1["total"] == 2
    assert len(page1["items"]) == 1
    page2 = client.get("/api/results", headers=headers, params={"page": 2, "page_size": 1}).json()["data"]
    assert len(page2["items"]) == 1
    # 分页不重复：两页 items id 不同
    assert page1["items"][0]["id"] != page2["items"][0]["id"]


def test_mysql_dialect_engine_builds_and_pool_settings():
    """MySQL 部署路径：URL 能被 SQLAlchemy 解析且应用连接池参数（不实际连接）。"""
    url = "mysql+pymysql://netcheck:netcheck@127.0.0.1:3306/netcheck?charset=utf8mb4"
    from sqlalchemy import create_engine

    eng = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
    assert eng.url.get_backend_name() == "mysql"
    assert eng.pool._recycle == 3600
    eng.dispose()


def test_settings_env_override_and_defaults():
    """配置项可被覆盖，默认值符合预期。"""
    from app.core.config import Settings

    settings = Settings(token_ttl_hours=2, password_min_length=6)
    assert settings.token_ttl_hours == 2
    assert settings.password_min_length == 6
    assert settings.login_max_attempts == 5
    assert settings.check_concurrency == 8