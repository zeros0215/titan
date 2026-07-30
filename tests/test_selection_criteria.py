from types import SimpleNamespace
import unittest

from config.selection_criteria import SELECTION_CRITERIA
from domain.enums import MarketType
from filter.engine import FilterEngine
from market.context.market_context import MarketContext
from market.context.market_trend import MarketTrend
from prediction.prediction_engine import PredictionEngine
from prediction.prediction_grade import PredictionGrade
from scoring.score_constants import ScoreConstants
from scoring.score_result import ScoreResult


class SelectionCriteriaTest(unittest.TestCase):
    def test_score_budget_is_100_and_buy_threshold_is_reachable(self) -> None:
        score = ScoreResult(
            trend_score=30,
            momentum_score=15,
            volume_score=15,
            price_action_score=15,
            risk_score=15,
            context_score=10,
        )

        self.assertEqual(ScoreConstants.MAX_SCORE, 100)
        self.assertEqual(score.normalized_score, 100)
        self.assertEqual(
            PredictionEngine().predict(
                ScoreResult(
                    trend_score=30,
                    momentum_score=15,
                    volume_score=15,
                    risk_score=10,
                    context_score=10,
                )
            ).grade,
            PredictionGrade.BUY,
        )

    def test_filter_accepts_only_a_qualified_market_regime_candidate(self) -> None:
        accepted = self._candidate(MarketTrend.BULL, 8.0)
        bear_market = self._candidate(MarketTrend.BEAR, 8.0)
        overheated = self._candidate(MarketTrend.BULL, 13.0)

        result = FilterEngine().filter([accepted, bear_market, overheated])

        self.assertEqual(result, [accepted])

    @staticmethod
    def _candidate(trend: MarketTrend, momentum_5: float):
        context = MarketContext(
            kospi_trend=trend,
            kosdaq_trend=trend,
            market_strength=SELECTION_CRITERIA.minimum_market_strength,
            sector_strength=0.0,
            theme_strength=0.0,
            foreign_flow=0.0,
            institution_flow=0.0,
        )
        return SimpleNamespace(
            market=MarketType.KOSPI,
            context=context,
            score=ScoreResult(
                trend_score=30,
                momentum_score=15,
                volume_score=15,
                price_action_score=15,
                risk_score=15,
                context_score=10,
            ),
            indicators=SimpleNamespace(
                momentum=SimpleNamespace(momentum_5=momentum_5),
            ),
        )


if __name__ == "__main__":
    unittest.main()
