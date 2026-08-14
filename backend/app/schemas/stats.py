from pydantic import BaseModel


class RttTrendItem(BaseModel):
    date: str
    avg_response_ms: float | None
    max_response_ms: float | None


class AvailabilityItem(BaseModel):
    date: str
    total: int
    success: int
    rate: float


class RunDurationItem(BaseModel):
    run_id: int
    task_id: int
    task_name: str
    started_at: str | None
    duration_s: float | None
    status: str


class StatAssetItem(BaseModel):
    id: int
    name: str
    ip: str | None