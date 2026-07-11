from datetime import datetime

from pydantic import BaseModel


class GlobalResultOut(BaseModel):
    id: int
    run_id: int
    task_id: int
    task_name: str
    asset_id: int
    asset_name: str
    check_type: str
    target: str | None
    status: str
    response_time: float | None
    message: str | None
    error_message: str | None
    checked_at: datetime
