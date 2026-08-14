from datetime import datetime

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    username: str
    action: str
    target_type: str | None
    target_id: int | None
    detail: str | None
    ip: str | None
    created_at: datetime

    model_config = {"from_attributes": True}