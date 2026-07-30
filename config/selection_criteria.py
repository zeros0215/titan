from dataclasses import dataclass

from feature.feature_type import FeatureType


@dataclass(frozen=True, slots=True)
class SelectionCriteria:
    """V1 selection thresholds. Adjust this module to revise the strategy."""

    buy_score: int = 80
    watch_score: int = 65
    minimum_score: int = 80
    minimum_market_strength: float = 0.60
    maximum_momentum_5d: float = 12.0
    minimum_trend_score: int = 15
    minimum_risk_score: int = 5
    reject_combined_volatility_warnings: bool = False
    require_acceleration_or_volume_surge: bool = False


SELECTION_CRITERIA = SelectionCriteria()

# Category budgets sum to 100. Correlated signals share a category cap.
TREND_FEATURE_SCORES = {
    FeatureType.PRICE_ABOVE_MA20: 8,
    FeatureType.PRICE_ABOVE_MA60: 8,
    FeatureType.MA5_ABOVE_MA20: 7,
    FeatureType.MA20_ABOVE_MA60: 7,
    FeatureType.GOLDEN_CROSS: 10,
}
MOMENTUM_FEATURE_SCORES = {
    FeatureType.HIGH_MOMENTUM_5D: 5,
    FeatureType.HIGH_MOMENTUM_20D: 7,
    FeatureType.ACCELERATION: 5,
}
VOLUME_FEATURE_SCORES = {
    FeatureType.VOLUME_EXPLOSION: 6,
    FeatureType.HIGH_TRADING_VALUE: 5,
    FeatureType.VOLUME_CONTINUATION: 4,
}
PRICE_ACTION_FEATURE_SCORES = {
    FeatureType.NEW_HIGH: 15,
    FeatureType.BREAKOUT_60: 12,
    FeatureType.BREAKOUT_20: 10,
    FeatureType.HIGHER_HIGH: 5,
    FeatureType.HIGHER_LOW: 5,
    FeatureType.GAP_UP: 5,
    FeatureType.LONG_BULL_CANDLE: 5,
    FeatureType.SMALL_PULLBACK: 5,
    FeatureType.INSIDE_BAR: 5,
}
RISK_FEATURE_SCORES = {
    FeatureType.LOW_RISK: 7,
    FeatureType.LOW_VOLATILITY: 4,
    FeatureType.LOW_ATR: 4,
}

TREND_MAX_SCORE = 30
MOMENTUM_MAX_SCORE = 15
VOLUME_MAX_SCORE = 15
PRICE_ACTION_MAX_SCORE = 15
RISK_MAX_SCORE = 15
CONTEXT_MAX_SCORE = 10
