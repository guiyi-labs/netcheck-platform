"""第 1 批起新增业务接口统一采用 {code, message, data} 响应包络。

健康检查接口（/health、/api/health）保持原样直接返回字典，便于第 0 批测试不变。
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """统一响应包络。code=0 表示成功，非 0 表示业务错误。"""

    code: int = 0
    message: str = "ok"
    data: T | None = None


class PageData(BaseModel, Generic[T]):
    """分页数据载荷。"""

    total: int
    page: int
    page_size: int
    items: list[T]
