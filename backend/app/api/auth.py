from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ratelimit import is_locked, record_failure, remaining_lock_seconds, reset_failures
from app.core.security import generate_token, token_expires_at, utcnow, verify_password
from app.models.user import User
from app.schemas.common import Response
from app.schemas.user import LoginData, LoginRequest, UserInfo
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/login", response_model=Response[LoginData])
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Response[LoginData]:
    ip = _client_ip(request)
    if is_locked(payload.username, ip):
        wait = remaining_lock_seconds(payload.username, ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录失败次数过多，账号已锁定，请 {wait} 秒后重试",
        )
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
        record_failure(payload.username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    reset_failures(payload.username, ip)
    token = generate_token()
    user.api_token = token
    user.api_token_expires_at = token_expires_at()
    user.last_login_at = utcnow()
    audit.record(db, user.username, "auth.login", detail="用户登录成功", request=request)
    db.commit()
    return Response(data=LoginData(token=token, user=UserInfo.model_validate(user)))


@router.post("/logout", response_model=Response)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    username = user.username
    user.api_token = None
    user.api_token_expires_at = None
    audit.record(db, username, "auth.logout", detail="用户退出登录")
    db.commit()
    return Response(message="已退出登录")


@router.get("/me", response_model=Response[UserInfo])
def me(user: User = Depends(get_current_user)) -> Response[UserInfo]:
    return Response(data=UserInfo.model_validate(user))


@router.post("/change-password", response_model=Response)
def change_password(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    from app.core.security import check_password_policy, hash_password, verify_password

    old_password = (payload.get("old_password") or "").strip()
    new_password = payload.get("new_password") or ""
    if not verify_password(old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    policy_error = check_password_policy(new_password)
    if policy_error:
        raise HTTPException(status_code=422, detail=policy_error)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    # 改密后使旧 token 失效，强制重新登录
    user.api_token = None
    user.api_token_expires_at = None
    db.commit()
    return Response(message="密码已修改，请重新登录")