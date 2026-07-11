from datetime import datetime

from pydantic import BaseModel


class DashboardCountItem(BaseModel):
    name: str
    count: int


class DashboardSummary(BaseModel):
    asset_total: int
    online_assets: int
    offline_assets: int
    warning_assets: int
    unknown_assets: int
    task_total: int
    run_total: int
    today_runs: int
    today_abnormal_results: int
    diagnosis_total: int
    active_alerts: int
    unconfirmed_alerts: int
    recovered_alerts_today: int


class DashboardTrendItem(BaseModel):
    date: str
    runs: int
    abnormal_results: int


class RecentAbnormalItem(BaseModel):
    id: int
    run_id: int
    task_id: int
    task_name: str
    asset_id: int
    asset_name: str
    check_type: str
    status: str
    target: str | None
    message: str | None
    error_message: str | None
    checked_at: datetime
