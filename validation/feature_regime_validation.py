from dataclasses import dataclass

from feature.feature_type import FeatureType
from market.context.market_regime import MarketRegime


@dataclass(slots=True, frozen=True)
class FeatureRegimeValidation:
    feature_type: FeatureType
    regime: MarketRegime
    total_count: int
    success_count: int
    average_return: float
    average_gross_return: float
    average_benchmark_return: float | None = None
    average_excess_return: float | None = None

    @property
    def win_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0
