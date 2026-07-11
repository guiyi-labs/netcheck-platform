from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    additions = {
        "inspection_tasks": [
            ("schedule_enabled", "BOOLEAN DEFAULT 0"),
            ("schedule_interval_minutes", "INTEGER"),
            ("next_run_at", "DATETIME"),
            ("last_scheduled_run_at", "DATETIME"),
        ],
        "inspection_runs": [("trigger_type", "VARCHAR(16) DEFAULT 'manual'")],
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not existing:
                continue
            for name, definition in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


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
    from app.models import discovery as _discovery  # noqa: F401
    from app.models import inspection as _inspection  # noqa: F401
    from app.models import report as _report  # noqa: F401
    from app.models import user as _user  # noqa: F401
    from app.models.base import Base
    from app.seed import seed_demo_data

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
    seed_demo_data(SessionLocal)
