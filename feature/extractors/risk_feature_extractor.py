from math import sqrt

from domain.candle_series import CandleSeries
from feature.extractors.base_extractor import BaseFeatureExtractor
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from indicators.bundle import IndicatorBundle


class RiskFeatureExtractor(BaseFeatureExtractor):
    """Converts downside, volatility, and ATR measures into risk features."""

    def extract(
        self,
        series: CandleSeries,
        indicators: IndicatorBundle,
        features: FeatureSet,
    ) -> None:
        change_20d = indicators.risk.change_20d
        low_risk = change_20d >= -0.05
        self.add_feature(
            features,
            FeatureType.LOW_RISK,
            low_risk,
            min(max((change_20d + 0.05) / 0.15, 0.0), 1.0),
            change_20d,
            "20-day downside is contained",
            "20-day downside exceeds the risk threshold",
        )

        volatility = self._daily_volatility(series)
        low_volatility = volatility <= 0.03
        self.add_feature(
            features,
            FeatureType.LOW_VOLATILITY,
            low_volatility,
            max(0.0, 1.0 - volatility / 0.03),
            volatility,
            "daily volatility is contained",
            "daily volatility exceeds the risk threshold",
        )

        atr_ratio = self._atr_ratio(series)
        low_atr = atr_ratio <= 0.04
        self.add_feature(
            features,
            FeatureType.LOW_ATR,
            low_atr,
            max(0.0, 1.0 - atr_ratio / 0.04),
            atr_ratio,
            "ATR is contained relative to price",
            "ATR is elevated relative to price",
        )

    @staticmethod
    def _daily_volatility(series: CandleSeries) -> float:
        closes = series.closes
        returns = [
            closes[index] / closes[index - 1] - 1
            for index in range(1, len(closes))
            if closes[index - 1] > 0
        ]
        return sqrt(sum(value * value for value in returns) / len(returns)) if returns else 0.0

    @staticmethod
    def _atr_ratio(series: CandleSeries, period: int = 14) -> float:
        candles = series.candles
        if len(candles) < 2 or series.latest.close <= 0:
            return 0.0

        ranges = [
            max(
                candle.high - candle.low,
                abs(candle.high - previous.close),
                abs(candle.low - previous.close),
            )
            for previous, candle in zip(candles[-period - 1:-1], candles[-period:])
        ]
        return sum(ranges) / len(ranges) / series.latest.close if ranges else 0.0
