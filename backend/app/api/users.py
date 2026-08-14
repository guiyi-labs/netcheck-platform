"""用户管理：仅管理员可用。支持账号的创建、角色/启用状态调整、改密与删除。"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.core.security import check_password_policy, hash_password
from app.models.user import User
from app.schemas.common import PageData, Response
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import audit

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(get_current_user)])

ROLE_LABELS = {"admin": "管理员", "operator": "运维操作员", "viewer": "只读观察员"}


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("", response_model=Response[PageData[UserOut]])
def list_users(
    page: int = 1,
    page_size: int = 20,
    username: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response[PageData[UserOut]]:
    query = db.query(User)
    if username:
        query = query.filter(User.username.like(f"%{username}%"))
    total = query.count()
    items = query.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[_user_out(item) for item in items]))


@router.post("", response_model=Response[UserOut], status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response[UserOut]:
    policy_error = check_password_policy(payload.password)
    if policy_error:
        raise HTTPException(status_code=422, detail=policy_error)
    if db.query(User).filter(User.username == payload.username).first() is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        must_change_password=payload.must_change_password,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        current_user.username,
        "user.create",
        target_type="user",
        target_id=user.id,
        detail=f"创建用户 {user.username}（{ROLE_LABELS.get(user.role, user.role)}）",
        request=request,
    )
    db.commit()
    db.refresh(user)
    return Response(message="用户已创建", data=_user_out(user))


@router.put("/{user_id}", response_model=Response[UserOut])
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response[UserOut]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.is_active is not None:
        if user.id == current_user.id and not payload.is_active:
            raise HTTPException(status_code=422, detail="不能停用自己的账号")
        user.is_active = payload.is_active
    if payload.role is not None:
        if user.id == current_user.id and payload.role != "admin":
            raise HTTPException(status_code=422, detail="不能降低自己的权限")
        user.role = payload.role
    if payload.password:
        policy_error = check_password_policy(payload.password)
        if policy_error:
            raise HTTPException(status_code=422, detail=policy_error)
        user.password_hash = hash_password(payload.password)
        user.api_token = None
        user.api_token_expires_at = None
    audit.record(
        db,
        current_user.username,
        "user.update",
        target_type="user",
        target_id=user.id,
        detail=f"更新用户 {user.username}：角色={user.role} 启用={user.is_active}",
        request=request,
    )
    db.commit()
    db.refresh(user)
    return Response(message="用户已更新", data=_user_out(user))


@router.delete("/{user_id}", response_model=Response[UserOut])
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response[UserOut]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=422, detail="不能删除自己的账号")
    data = _user_out(user)
    audit.record(
        db,
        current_user.username,
        "user.delete",
        target_type="user",
        target_id=user.id,
        detail=f"删除用户 {user.username}",
        request=request,
    )
    db.delete(user)
    db.commit()
    return Response(message="用户已删除", data=data)