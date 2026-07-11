from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    role: str

    model_config = {"from_attributes": True}


class LoginData(BaseModel):
    token: str
    user: UserInfo
