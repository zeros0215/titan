import unittest

from market.context.market_context import MarketContext
from market.context.market_regime import MarketRegime, MarketRegimeClassifier
from market.context.market_trend import MarketTrend


class MarketRegimeClassifierTest(unittest.TestCase):
    def test_classifies_supported_context_regimes(self) -> None:
        self.assertEqual(
            MarketRegimeClassifier.classify(
                self._context(MarketTrend.BULL, MarketTrend.BULL, 0.8)
            ),
            MarketRegime.BULL,
        )
        self.assertEqual(
            MarketRegimeClassifier.classify(
                self._context(MarketTrend.BEAR, MarketTrend.BEAR, 0.2)
            ),
            MarketRegime.BEAR,
        )
        self.assertEqual(
            MarketRegimeClassifier.classify(
                self._context(
                    MarketTrend.SIDEWAYS,
                    MarketTrend.SIDEWAYS,
                    0.5,
                )
            ),
            MarketRegime.SIDEWAYS,
        )
        self.assertEqual(
            MarketRegimeClassifier.classify(
                self._context(MarketTrend.BULL, MarketTrend.BEAR, 0.5)
            ),
            MarketRegime.MIXED,
        )

    @staticmethod
    def _context(kospi, kosdaq, strength) -> MarketContext:
        return MarketContext(
            kospi,
            kosdaq,
            strength,
            0.0,
            0.0,
            0.0,
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
