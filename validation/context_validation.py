from dataclasses import dataclass

from market.context.market_regime import MarketRegime


@dataclass(slots=True, frozen=True)
class ContextValidation:
    regime: MarketRegime
    total_count: int
    success_count: int
    average_return: float
    average_gross_return: float
    average_benchmark_return: float | None = None
    average_excess_return: float | None = None
    average_market_strength: float = 0.0
    average_context_score: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0
