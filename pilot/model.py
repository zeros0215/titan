from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True, frozen=True)
class KisPilotResult:
    run_id: str
    as_of: datetime
    status: str
    duration_seconds: float
    universe_count: int
    analyzed_count: int
    selection_count: int
    observation_count: int
    excluded_count: int
    exclusion_rate: float
    fetch_failures: dict[str, str]
    request_count: int
    success_count: int
    retry_count: int
    retry_rate: float
    failure_count: int
    server_error_count: int
    transport_error_count: int
    api_success_rate: float
    order_request_count: int = 0
    selected_candidates: list[dict] = field(default_factory=list)
    observation_candidates: list[dict] = field(default_factory=list)
    snapshot_path: Path | None = None
    report_path: Path | None = None
    reasons: list[str] = field(default_factory=list)
    strategy_version: str = "V1.1"
    source: str = "KIS"
