from dataclasses import dataclass

from backtest.model.backtest_result import BacktestResult
from backtest.model.selection import Selection
from validation.validation_result import ValidationResult


@dataclass(slots=True, frozen=True)
class DeferredValidationResult:
    """Artifacts produced by validating a previously stored selection run."""

    selections: list[Selection]
    backtest: BacktestResult
    validation: ValidationResult
    report_markdown: str
