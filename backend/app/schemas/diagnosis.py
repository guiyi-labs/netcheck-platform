from datetime import datetime

from pydantic import BaseModel


class DiagnosisOut(BaseModel):
    id: int
    run_id: int
    result_id: int | None
    asset_id: int
    check_type: str
    fault_type: str
    severity: str
    suggestion: str
    evidence: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
