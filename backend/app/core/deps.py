from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import utcnow
from app.models.user import User

# auto_error=False 让缺失 token 时由我们自己抛 401，便于统一响应
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
        )
    user = db.query(User).filter(User.api_token == credentials.credentials).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证令牌无效或已过期",
        )
    # token 过期检查：api_token_expires_at 为 None 视为兼容旧数据（永不过期）
    if user.api_token_expires_at is not None and user.api_token_expires_at <= utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证令牌已过期，请重新登录",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号已被停用，请联系管理员",
        )
    return user


def require_write(current_user: User = Depends(get_current_user)) -> User:
    """所有写操作依赖：viewer（只读）角色无权执行。"""
    if current_user.role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只读用户无权执行此操作",
        )
    return current_user


def require_operator_admin(current_user: User = Depends(get_current_user)) -> User:
    """敏感配置内容读取依赖：仅 operator / admin 可读（N2.1 P1）。"""
    if current_user.role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="查看者无权读取敏感配置内容",
        )
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """用户管理、系统配置等仅管理员可执行。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user