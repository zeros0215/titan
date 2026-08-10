from config.selection_criteria import SELECTION_CRITERIA
from domain.enums import MarketType
from feature.feature_type import FeatureType
from market.context.market_trend import MarketTrend
from config.sector_groups import SECTOR_GROUPS


SECTOR_BY_CODE = {
    code: group
    for group, members in SECTOR_GROUPS.items()
    for code in members
}


class FilterEngine:
    """Applies hard eligibility rules before ranking eligible candidates."""

    def __init__(self, criteria=SELECTION_CRITERIA) -> None:
        self.criteria = criteria

    def filter(self, results):
        eligible = [item for item in results if self._is_eligible(item)]
        if self.criteria.research_peer_filter is None:
            return eligible
        if self.criteria.research_peer_filter != "strong_industry_top30":
            raise ValueError(
                f"unknown research peer filter: {self.criteria.research_peer_filter}"
            )
        peer_codes = {
            item.code for item in self._strong_industry_top30(results)
        }
        return [item for item in eligible if item.code in peer_codes]

    def _is_eligible(self, item) -> bool:
        score = item.score
        context = item.context
        trend = self._trend(item)
        minimum_score = self._minimum_score(context, trend)
        credit = self.criteria.research_breakout_threshold_credit
        if credit and (
            item.features.contains(FeatureType.NEW_HIGH)
            or item.features.contains(FeatureType.BREAKOUT_20)
        ):
            minimum_score = max(0, minimum_score - credit)
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

        if not self._passes_research_market_filter(item, trend):
            return False
        if not self._passes_research_entry_filter(item):
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

    def _passes_research_market_filter(self, item, trend) -> bool:
        mode = self.criteria.research_market_filter
        if mode is None or mode == "baseline":
            return True
        context = item.context
        short_regime = self.short_market_regime(item)
        if mode == "exclude_short_slowdown":
            return short_regime == "BULL"
        if mode == "strong_continuation":
            return (
                trend == MarketTrend.BULL
                and context.market_strength >= self.criteria.strong_market_strength
                and short_regime == "BULL"
            )
        if mode == "continuation_momentum20":
            return (
                short_regime == "BULL"
                and item.features.contains(FeatureType.HIGH_MOMENTUM_20D)
            )
        raise ValueError(f"unknown research market filter: {mode}")

    def _passes_research_entry_filter(self, item) -> bool:
        mode = self.criteria.research_entry_filter
        if mode is None:
            return True
        if mode == "new_high_or_breakout20":
            return (
                item.features.contains(FeatureType.NEW_HIGH)
                or item.features.contains(FeatureType.BREAKOUT_20)
            )
        if mode == "recent_breakout_pullback":
            return item.features.contains(
                FeatureType.RECENT_BREAKOUT_PULLBACK
            )
        if mode == "confirmed_breakout_pullback":
            return item.features.contains(
                FeatureType.CONFIRMED_BREAKOUT_PULLBACK
            )
        if mode == "volume_confirmed_breakout_pullback":
            return item.features.contains(
                FeatureType.VOLUME_CONFIRMED_BREAKOUT_PULLBACK
            )
        if mode == "first_volume_breakout20":
            return item.features.contains(
                FeatureType.FIRST_VOLUME_BREAKOUT_20
            )
        raise ValueError(f"unknown research entry filter: {mode}")

    @staticmethod
    def _strong_industry_top30(items):
        groups = {}
        for item in items:
            group = SECTOR_BY_CODE.get(item.code)
            if group is not None:
                groups.setdefault(group, []).append(item)
        accepted = []
        for members in groups.values():
            if len(members) < 3:
                continue
            ordered = sorted(
                members,
                key=lambda item: item.indicators.momentum.momentum_20,
                reverse=True,
            )
            industry_momentum = sum(
                item.indicators.momentum.momentum_20 for item in members
            ) / len(members)
            if industry_momentum <= 0:
                continue
            limit = max(1, (len(ordered) * 30 + 99) // 100)
            accepted.extend(ordered[:limit])
        return accepted

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
