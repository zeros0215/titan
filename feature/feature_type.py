from enum import Enum

from feature.feature_category import FeatureCategory


class FeatureType(Enum):
    """
    Feature 종류

    Indicator의 계산 결과를 사람이 이해할 수 있는 투자 신호로 변환한다.
    """

    # ==========================
    # Trend
    # ==========================
    PRICE_ABOVE_MA20 = "PRICE_ABOVE_MA20"
    PRICE_ABOVE_MA60 = "PRICE_ABOVE_MA60"

    MA5_ABOVE_MA20 = "MA5_ABOVE_MA20"
    MA20_ABOVE_MA60 = "MA20_ABOVE_MA60"

    GOLDEN_CROSS = "GOLDEN_CROSS"
    DEAD_CROSS = "DEAD_CROSS"

    # ==========================
    # Momentum
    # ==========================
    HIGH_MOMENTUM_5D = "HIGH_MOMENTUM_5D"
    HIGH_MOMENTUM_20D = "HIGH_MOMENTUM_20D"

    ACCELERATION = "ACCELERATION"

    # ==========================
    # Volume
    # ==========================
    VOLUME_EXPLOSION = "VOLUME_EXPLOSION"
    HIGH_TRADING_VALUE = "HIGH_TRADING_VALUE"
    VOLUME_CONTINUATION = "VOLUME_CONTINUATION"

    # ==========================
    # Breakout
    # ==========================
    BREAKOUT_20 = "BREAKOUT_20"
    BREAKOUT_60 = "BREAKOUT_60"

    NEW_HIGH = "NEW_HIGH"

    # ==========================
    # Risk
    # ==========================
    LOW_RISK = "LOW_RISK"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    LOW_ATR = "LOW_ATR"

    # ==========================
    # Price Action
    # ==========================
    HIGHER_HIGH = "HIGHER_HIGH"
    HIGHER_LOW = "HIGHER_LOW"

    GAP_UP = "GAP_UP"

    LONG_BULL_CANDLE = "LONG_BULL_CANDLE"
    SMALL_PULLBACK = "SMALL_PULLBACK"
    RECENT_BREAKOUT_PULLBACK = "RECENT_BREAKOUT_PULLBACK"
    CONFIRMED_BREAKOUT_PULLBACK = "CONFIRMED_BREAKOUT_PULLBACK"
    VOLUME_CONFIRMED_BREAKOUT_PULLBACK = "VOLUME_CONFIRMED_BREAKOUT_PULLBACK"
    FIRST_VOLUME_BREAKOUT_20 = "FIRST_VOLUME_BREAKOUT_20"

    INSIDE_BAR = "INSIDE_BAR"

    @property
    def category(self) -> FeatureCategory:
        return FEATURE_CATEGORY_MAP[self]


FEATURE_CATEGORY_MAP = {

    # ==========================
    # Trend
    # ==========================
    FeatureType.PRICE_ABOVE_MA20: FeatureCategory.TREND,
    FeatureType.PRICE_ABOVE_MA60: FeatureCategory.TREND,
    FeatureType.MA5_ABOVE_MA20: FeatureCategory.TREND,
    FeatureType.MA20_ABOVE_MA60: FeatureCategory.TREND,
    FeatureType.GOLDEN_CROSS: FeatureCategory.TREND,
    FeatureType.DEAD_CROSS: FeatureCategory.TREND,

    # ==========================
    # Momentum
    # ==========================
    FeatureType.HIGH_MOMENTUM_5D: FeatureCategory.MOMENTUM,
    FeatureType.HIGH_MOMENTUM_20D: FeatureCategory.MOMENTUM,
    FeatureType.ACCELERATION: FeatureCategory.MOMENTUM,

    # ==========================
    # Volume
    # ==========================
    FeatureType.VOLUME_EXPLOSION: FeatureCategory.VOLUME,
    FeatureType.HIGH_TRADING_VALUE: FeatureCategory.VOLUME,
    FeatureType.VOLUME_CONTINUATION: FeatureCategory.VOLUME,

    # ==========================
    # Price Action
    # ==========================
    FeatureType.BREAKOUT_20: FeatureCategory.PRICE_ACTION,
    FeatureType.BREAKOUT_60: FeatureCategory.PRICE_ACTION,
    FeatureType.NEW_HIGH: FeatureCategory.PRICE_ACTION,

    FeatureType.HIGHER_HIGH: FeatureCategory.PRICE_ACTION,
    FeatureType.HIGHER_LOW: FeatureCategory.PRICE_ACTION,

    FeatureType.GAP_UP: FeatureCategory.PRICE_ACTION,
    FeatureType.LONG_BULL_CANDLE: FeatureCategory.PRICE_ACTION,
    FeatureType.SMALL_PULLBACK: FeatureCategory.PRICE_ACTION,
    FeatureType.RECENT_BREAKOUT_PULLBACK: FeatureCategory.PRICE_ACTION,
    FeatureType.CONFIRMED_BREAKOUT_PULLBACK: FeatureCategory.PRICE_ACTION,
    FeatureType.VOLUME_CONFIRMED_BREAKOUT_PULLBACK: FeatureCategory.PRICE_ACTION,
    FeatureType.FIRST_VOLUME_BREAKOUT_20: FeatureCategory.PRICE_ACTION,
    FeatureType.INSIDE_BAR: FeatureCategory.PRICE_ACTION,

    # ==========================
    # Risk
    # ==========================
    FeatureType.LOW_RISK: FeatureCategory.RISK,
    FeatureType.LOW_VOLATILITY: FeatureCategory.RISK,
    FeatureType.LOW_ATR: FeatureCategory.RISK,
}
