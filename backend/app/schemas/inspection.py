from datetime import datetime

from pydantic import BaseModel, Field


CHECK_TYPES = {"ping", "port", "http", "dns", "tls"}


class TaskBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    check_types: list[str] = Field(min_length=1)
    asset_ids: list[int] = Field(min_length=1)
    enabled: bool = True
    schedule_enabled: bool = False
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    schedule_cron: str | None = Field(default=None, max_length=128)


class TaskCreate(TaskBase):
    pass


class TaskUpdate(TaskBase):
    pass


class TaskOut(TaskBase):
    id: int
    next_run_at: datetime | None
    last_scheduled_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: int
    task_id: int
    status: str
    trigger_type: str
    cancel_requested: bool
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class ResultOut(BaseModel):
    id: int
    run_id: int
    asset_id: int
    check_type: str
    target: str | None
    status: str
    response_time: float | None
    message: str | None
    error_message: str | None
    checked_at: datetime

    model_config = {"from_attributes": True}
