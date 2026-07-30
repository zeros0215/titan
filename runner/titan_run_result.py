from dataclasses import dataclass

from backtest.model.backtest_result import BacktestResult
from backtest.model.selection import Selection
from ranking.ranking_result import RankingResult
from validation.validation_result import ValidationResult


@dataclass(slots=True, frozen=True)
class TitanRunResult:
    """Artifacts produced by one complete TITAN selection run."""

    ranking: RankingResult
    selections: list[Selection]
    backtest: BacktestResult
    validation: ValidationResult
    report_markdown: str
