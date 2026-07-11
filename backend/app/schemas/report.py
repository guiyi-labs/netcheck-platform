from datetime import date, datetime

from pydantic import BaseModel, Field


class ReportGenerateIn(BaseModel):
    report_type: str = Field(pattern="^(run|daily)$")
    run_id: int | None = None
    report_date: date | None = None


class ReportOut(BaseModel):
    id: int
    report_name: str
    report_type: str
    report_date: str
    run_id: int | None
    task_id: int | None
    file_name: str
    file_path: str
    file_size: int
    created_at: datetime

    model_config = {"from_attributes": True}
