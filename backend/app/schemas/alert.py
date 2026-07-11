from datetime import datetime

from pydantic import BaseModel, Field


ALERT_STATUSES = {"active", "confirmed", "recovered"}


class AlertOut(BaseModel):
    id: int
    asset_id: int
    run_id: int
    result_id: int | None
    diagnosis_id: int | None
    alert_title: str
    alert_level: str
    alert_status: str
    alert_key: str
    check_type: str
    fault_type: str
    evidence: str | None
    suggestion: str | None
    first_triggered_at: datetime
    last_triggered_at: datetime
    trigger_count: int
    consecutive_failures: int
    consecutive_successes: int
    confirmed_by: str | None
    confirmed_at: datetime | None
    recovered_at: datetime | None
    recovery_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertPolicyOut(BaseModel):
    id: int
    name: str
    enabled: bool
    slow_response_threshold: int
    failure_threshold: int
    recovery_threshold: int
    deduplicate_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    slow_response_threshold: int | None = Field(default=None, ge=1)
    failure_threshold: int | None = Field(default=None, ge=1)
    recovery_threshold: int | None = Field(default=None, ge=1)
    deduplicate_enabled: bool | None = None


class AlertRecoverRequest(BaseModel):
    recovery_reason: str | None = None


class AlertSummary(BaseModel):
    active_alerts: int
    unconfirmed_alerts: int
    recovered_alerts_today: int
