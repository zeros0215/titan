from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backtest.model.selection import Selection


@dataclass(slots=True)
class SelectionResult:
    """
    Selection 검증 결과.

    Analyzer가 선택한 종목의
    실제 성과(Fact)만 저장한다.

    성공/실패 판단은 Validation에서 수행한다.
    """

    selection: Selection

    evaluation_date: datetime

    holding_days: int

    selection_price: float

    evaluation_price: float

    return_rate: float

    net_return_rate: float | None = None

    benchmark_return_rate: float | None = None

    excess_return_rate: float | None = None

    @property
    def code(self) -> str:
        return self.selection.code

    @property
    def name(self) -> str:
        return self.selection.name

    @property
    def rank(self) -> int:
        return self.selection.rank

    @property
    def effective_return_rate(self) -> float:
        """Return the cost-adjusted result when available."""
        return (
            self.net_return_rate
            if self.net_return_rate is not None
            else self.return_rate
        )
