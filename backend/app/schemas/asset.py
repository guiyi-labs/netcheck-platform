from datetime import datetime

from pydantic import BaseModel, Field


class AssetBase(BaseModel):
    name: str
    ip: str
    hostname: str | None = None
    asset_type: str
    location: str | None = None
    os_type: str | None = None
    business_name: str | None = None
    ports: str | None = None
    owner: str | None = None
    status: str = "unknown"
    remark: str | None = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(AssetBase):
    pass


class AssetOut(AssetBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssetMeta(BaseModel):
    asset_types: list[str]
    statuses: list[str]


# 资产类型与状态常量，前端下拉与后端校验共用
ASSET_TYPES = [
    "server",
    "network_device",
    "web_service",
    "database_service",
    "middleware",
    "terminal",
    "container",
]

ASSET_STATUSES = ["online", "offline", "warning", "unknown"]
