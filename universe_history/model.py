from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from domain.enums import MarketType


@dataclass(slots=True, frozen=True)
class UniverseHistoryRecord:
    code: str
    name: str
    market: MarketType
    effective_from: date
    effective_to: date | None
    source_id: str


class IssueSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(slots=True, frozen=True)
class UniverseHistoryIssue:
    severity: IssueSeverity
    code: str
    message: str
    stock_code: str | None = None


@dataclass(slots=True, frozen=True)
class UniverseHistoryValidation:
    record_count: int
    stock_count: int
    issues: list[UniverseHistoryIssue] = field(default_factory=list)

    @property
    def errors(self):
        return [
            item for item in self.issues
            if item.severity is IssueSeverity.ERROR
        ]

    @property
    def warnings(self):
        return [
            item for item in self.issues
            if item.severity is IssueSeverity.WARNING
        ]

    @property
    def is_valid(self) -> bool:
        return not self.errors
