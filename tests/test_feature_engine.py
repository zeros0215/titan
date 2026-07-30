from datetime import datetime, timedelta
import unittest

from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.enums import MarketType
from domain.stock import Stock
from feature.feature_engine import FeatureEngine
from feature.feature_type import FeatureType
from indicators.calculator import IndicatorCalculator
from scoring.score_engine import ScoreEngine


class FeatureEngineTest(unittest.TestCase):
    def test_emits_price_action_and_risk_features_used_by_score_policies(self) -> None:
        series = self._stable_series()
        indicators = IndicatorCalculator().calculate(series)

        features = FeatureEngine().extract(series, indicators)
        score = ScoreEngine().calculate(features)

        self.assertTrue(features.contains(FeatureType.NEW_HIGH))
        self.assertTrue(features.contains(FeatureType.BREAKOUT_20))
        self.assertTrue(features.contains(FeatureType.LOW_RISK))
        self.assertTrue(features.contains(FeatureType.LOW_VOLATILITY))
        self.assertTrue(features.contains(FeatureType.LOW_ATR))
        self.assertEqual(score.price_action_score, 15)
        self.assertGreater(score.risk_score, 0)

    @staticmethod
    def _stable_series() -> CandleSeries:
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        candles = [
            Candle(
                date=datetime(2026, 1, 1) + timedelta(days=index),
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1_000_000,
            )
            for index in range(61)
        ]
        return CandleSeries(stock, candles)


if __name__ == "__main__":
    unittest.main()
