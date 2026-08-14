from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

if settings.database_url.startswith("sqlite"):
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
else:
    # MySQL/其他关系库：连接池探活与回收，避免长连接失效
    engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    additions = {
        "users": [
            ("api_token_expires_at", "DATETIME"),
            ("must_change_password", "BOOLEAN DEFAULT 0"),
            ("is_active", "BOOLEAN DEFAULT 1"),
        ],
        "inspection_tasks": [
            ("schedule_enabled", "BOOLEAN DEFAULT 0"),
            ("schedule_interval_minutes", "INTEGER"),
            ("schedule_cron", "VARCHAR(128)"),
            ("next_run_at", "DATETIME"),
            ("last_scheduled_run_at", "DATETIME"),
        ],
        "inspection_runs": [
            ("trigger_type", "VARCHAR(16) DEFAULT 'manual'"),
            ("cancel_requested", "BOOLEAN DEFAULT 0"),
        ],
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not existing:
                continue
            for name, definition in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def _ensure_sqlite_indexes() -> None:
    """为历史 SQLite 库补齐新增的组合索引（新库由 create_all 自动建立）。"""
    if not settings.database_url.startswith("sqlite"):
        return
    statements = [
        "CREATE INDEX IF NOT EXISTS ix_results_run_status ON inspection_results (run_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_results_asset_checked ON inspection_results (asset_id, checked_at)",
        "CREATE INDEX IF NOT EXISTS ix_results_checked_at ON inspection_results (checked_at)",
        "CREATE INDEX IF NOT EXISTS ix_runs_task_status ON inspection_runs (task_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_alerts_key_status ON alerts (alert_key, alert_status)",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """启动时建表并写入演示数据。幂等：仅在表为空时插入。"""
    # 显式导入模型，确保 Base.metadata 注册全部表
    from app.models import alert as _alert  # noqa: F401
    from app.models import asset as _asset  # noqa: F401
    from app.models import audit as _audit  # noqa: F401
    from app.models import discovery as _discovery  # noqa: F401
    from app.models import inspection as _inspection  # noqa: F401
    from app.models import report as _report  # noqa: F401
    from app.models import user as _user  # noqa: F401
    from app.models.base import Base
    from app.seed import seed_demo_data

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
    _ensure_sqlite_indexes()
    seed_demo_data(SessionLocal)
