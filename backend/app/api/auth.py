from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import generate_token, verify_password
from app.models.user import User
from app.schemas.common import Response
from app.schemas.user import LoginData, LoginRequest, UserInfo

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Response[LoginData])
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Response[LoginData]:
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    token = generate_token()
    user.api_token = token
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return Response(data=LoginData(token=token, user=UserInfo.model_validate(user)))


@router.post("/logout", response_model=Response)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    user.api_token = None
    db.commit()
    return Response(message="已退出登录")


@router.get("/me", response_model=Response[UserInfo])
def me(user: User = Depends(get_current_user)) -> Response[UserInfo]:
    return Response(data=UserInfo.model_validate(user))
