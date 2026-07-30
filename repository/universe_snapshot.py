from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from domain.stock import Stock


class UniverseCoverage(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True, frozen=True)
class UniverseSnapshot:
    as_of: datetime
    stocks: list[Stock]
    source_count: int
    dated_count: int
    excluded_before_listing: int
    excluded_after_delisting: int
    coverage: UniverseCoverage
    point_in_time_complete: bool

    @property
    def active_count(self) -> int:
        return len(self.stocks)

    @property
    def unknown_date_count(self) -> int:
        return self.source_count - self.dated_count
