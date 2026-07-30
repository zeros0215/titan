from dataclasses import dataclass, field

from backtest.model.selection_result import SelectionResult


@dataclass(slots=True)
class BacktestResult:
    """
    백테스트 전체 결과.
    """

    results: list[SelectionResult] = field(default_factory=list)

    missing_price_codes: list[str] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def missing_price_count(self) -> int:
        return len(self.missing_price_codes)
