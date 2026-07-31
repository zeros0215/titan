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
        trend = self._trend(item)
        minimum_score = self._minimum_score(context, trend)
        if score.normalized_score < minimum_score:
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

        if trend == MarketTrend.BEAR:
            return False

        momentum_5d = item.indicators.momentum.momentum_5
        maximum_momentum = self.criteria.maximum_momentum_5d
        if (
            self.criteria.use_market_regime_rules
            and trend == MarketTrend.SIDEWAYS
        ):
            maximum_momentum = min(
                maximum_momentum,
                self.criteria.sideways_maximum_momentum_5d,
            )
        return momentum_5d <= maximum_momentum

    def selection_limit(self, items, requested_limit: int) -> int:
        if not self.criteria.use_market_regime_rules or not items:
            return requested_limit
        regimes = {
            self.market_regime(item)
            for item in items
        }
        if self.criteria.use_short_term_market_overlay:
            long_regime = self.market_regime(items[0])
            short_regime = self.short_market_regime(items[0])
            if long_regime == "BEAR":
                return 0
            if long_regime == "SIDEWAYS":
                return min(requested_limit, 2) if short_regime == "BULL" else 0
            if short_regime == "BEAR":
                return min(requested_limit, 2)
            if short_regime == "SIDEWAYS":
                return min(requested_limit, 3)
        if "STRONG_BULL" in regimes:
            return requested_limit
        if "BULL" in regimes:
            return min(requested_limit, 5)
        if "SIDEWAYS" in regimes:
            return min(requested_limit, 3)
        return 0

    def market_regime(self, item) -> str:
        context = item.context
        trend = self._trend(item)
        if context is None or trend == MarketTrend.BEAR:
            return "BEAR"
        if (
            trend == MarketTrend.BULL
            and context.market_strength
            >= self.criteria.strong_market_strength
        ):
            return "STRONG_BULL"
        return trend.value

    def short_market_regime(self, item) -> str:
        context = item.context
        if context is None:
            return "BEAR"
        trend = (
            context.kospi_short_trend
            if item.market == MarketType.KOSPI
            else context.kosdaq_short_trend
        )
        if trend is None:
            return "BEAR"
        return trend.value

    def _minimum_score(self, context, trend) -> int:
        minimum = self.criteria.minimum_score
        if not self.criteria.use_market_regime_rules or context is None:
            return minimum
        if (
            trend == MarketTrend.BULL
            and context.market_strength
            >= self.criteria.strong_market_strength
        ):
            return max(0, minimum + self.criteria.strong_score_adjustment)
        if trend == MarketTrend.SIDEWAYS:
            return min(100, minimum + self.criteria.sideways_score_adjustment)
        return minimum

    @staticmethod
    def _trend(item):
        context = item.context
        if context is None:
            return MarketTrend.BEAR
        return (
            context.kospi_trend
            if item.market == MarketType.KOSPI
            else context.kosdaq_trend
        )
