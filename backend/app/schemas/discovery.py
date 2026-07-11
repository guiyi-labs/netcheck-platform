from datetime import datetime

from pydantic import BaseModel, Field


class DiscoveryScanCreate(BaseModel):
    target_range: str = Field(min_length=1, max_length=512)
    scan_mode: str = "ping_port"
    ports: str | None = "80,443"


class DiscoveryResultOut(BaseModel):
    id: int
    scan_id: int
    ip: str
    hostname: str | None
    open_ports: str | None
    status: str
    already_exists: bool
    matched_asset_id: int | None
    imported_asset_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DiscoveryScanOut(BaseModel):
    id: int
    target_range: str
    scan_mode: str
    ports: str | None
    status: str
    total_targets: int
    discovered_count: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}
