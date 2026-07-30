from config.selection_criteria import SELECTION_CRITERIA
from domain.enums import MarketType
from feature.feature_type import FeatureType
from market.context.market_trend import MarketTrend


class FilterEngine:
    """Applies hard eligibility rules before ranking eligible candidates."""

    def __init__(self, criteria=SELECTION_CRITERIA) -> None:
        self.criteria = criteria

    def filter(self, results):
        return [item for item in results if self._is_eligible(item)]

    def _is_eligible(self, item) -> bool:
        score = item.score
        context = item.context
        if score.normalized_score < self.criteria.minimum_score:
            return False
        if score.trend_score < self.criteria.minimum_trend_score:
            return False
        if score.volume_score == 0:
            return False
        if score.risk_score < self.criteria.minimum_risk_score:
            return False
        if (
            self.criteria.reject_combined_volatility_warnings
            and not item.features.contains(FeatureType.LOW_VOLATILITY)
            and not item.features.contains(FeatureType.LOW_ATR)
        ):
            return False
        if (
            self.criteria.require_acceleration_or_volume_surge
            and not (
                item.features.contains(FeatureType.ACCELERATION)
                or item.features.contains(FeatureType.VOLUME_EXPLOSION)
            )
        ):
            return False
        if context is None or context.market_strength < self.criteria.minimum_market_strength:
            return False

        trend = (
            context.kospi_trend
            if item.market == MarketType.KOSPI
            else context.kosdaq_trend
        )
        if trend == MarketTrend.BEAR:
            return False

        momentum_5d = item.indicators.momentum.momentum_5
        return momentum_5d <= self.criteria.maximum_momentum_5d
