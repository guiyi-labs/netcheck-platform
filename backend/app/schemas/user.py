from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    password: str = Field(min_length=1)
    role: str = Field(default="operator", pattern=r"^(admin|operator|viewer)$")
    must_change_password: bool = False


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(admin|operator|viewer)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=1)


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class LoginData(BaseModel):
    token: str
    user: UserInfo
