from dataclasses import dataclass, field

from validation.validation_result import ValidationResult
from walkforward.plan import WalkForwardFold


@dataclass(slots=True, frozen=True)
class WalkForwardFoldResult:
    fold: WalkForwardFold
    validations: list[ValidationResult] = field(default_factory=list)
    attempted_dates: int = 0
    completed_dates: int = 0
    errors: list[str] = field(default_factory=list)
    universe_coverages: list[str] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return sum(item.total_count for item in self.validations)

    @property
    def success_count(self) -> int:
        return sum(item.success_count for item in self.validations)

    @property
    def win_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0

    def weighted(self, attribute: str) -> float | None:
        available = [
            item
            for item in self.validations
            if getattr(item, attribute) is not None and item.total_count
        ]
        total = sum(item.total_count for item in available)
        if not total:
            return None
        return sum(
            getattr(item, attribute) * item.total_count
            for item in available
        ) / total


@dataclass(slots=True, frozen=True)
class WalkForwardResult:
    folds: list[WalkForwardFoldResult]
    strategy_version: str
    holding_days: int
    interval_months: int
    interval_days: int | None = None
    strategy_frozen: bool = True
    strategy_config_hash: str | None = None
