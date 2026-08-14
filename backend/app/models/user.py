from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """管理员账户。第 1 批只支持单管理员，token 直接挂在记录上。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="admin")
    # 是否允许登录：停用账号保留历史数据但无法登录
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 固定 token：登录时生成，登出时清空。同一用户同一时间只有一个有效 token。
    api_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # token 过期时间；为空表示旧数据兼容（不强制过期），新登录一律写入。
    api_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 是否强制下次登录后改密（管理员建号时可选）
    must_change_password: Mapped[bool] = mapped_column(default=False)
