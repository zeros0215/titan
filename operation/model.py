from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RunStatus(str, Enum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class RunRecord:
    run_id: str
    operation_date: datetime
    strategy_version: str
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    selection_count: int = 0
    observation_count: int = 0
    validation_count: int = 0
    skipped_validation_count: int = 0
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    forced: bool = False


@dataclass(frozen=True)
class OperationResult:
    record: RunRecord
    report_markdown: str
    run_path: object | None = None
    report_path: object | None = None
