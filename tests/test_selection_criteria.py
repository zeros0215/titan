from types import SimpleNamespace
import unittest

from config.selection_criteria import SELECTION_CRITERIA
from config.strategy_profiles import V1_3_S78_N7_CANDIDATE
from domain.enums import MarketType
from filter.engine import FilterEngine
from market.context.market_context import MarketContext
from market.context.market_trend import MarketTrend
from prediction.prediction_engine import PredictionEngine
from prediction.prediction_grade import PredictionGrade
from feature.feature_type import FeatureType
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

    def test_v13_changes_score_and_limit_by_market_regime(self) -> None:
        engine = FilterEngine(V1_3_S78_N7_CANDIDATE.criteria)
        strong = self._v13_candidate(MarketTrend.BULL, .75, 75, 10)
        normal = self._v13_candidate(MarketTrend.BULL, .65, 75, 10)
        sideways = self._v13_candidate(MarketTrend.SIDEWAYS, .65, 83, 8)
        sideways_hot = self._v13_candidate(
            MarketTrend.SIDEWAYS, .65, 83, 9
        )

        self.assertEqual(engine.filter([strong, normal]), [strong])
        self.assertEqual(engine.filter([sideways, sideways_hot]), [sideways])
        self.assertEqual(engine.selection_limit([strong], 7), 7)
        self.assertEqual(engine.selection_limit([normal], 7), 5)
        self.assertEqual(engine.selection_limit([sideways], 7), 3)

    def test_industry_peer_filter_keeps_positive_top_thirty_percent(self) -> None:
        members = []
        for code, momentum in (
            ("105560", 12.0),
            ("055550", 8.0),
            ("086790", 4.0),
            ("316140", 1.0),
        ):
            item = SimpleNamespace(
                code=code,
                indicators=SimpleNamespace(
                    momentum=SimpleNamespace(momentum_20=momentum),
                ),
            )
            members.append(item)

        result = FilterEngine._strong_industry_top30(members)

        self.assertEqual([item.code for item in result], ["105560", "055550"])

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

    @staticmethod
    def _v13_candidate(trend, strength, score, momentum_5):
        item = SelectionCriteriaTest._candidate(trend, momentum_5)
        item.context = MarketContext(
            kospi_trend=trend,
            kosdaq_trend=trend,
            market_strength=strength,
            sector_strength=0.0,
            theme_strength=0.0,
            foreign_flow=0.0,
            institution_flow=0.0,
        )
        item.score = ScoreResult(
            trend_score=30,
            momentum_score=10,
            volume_score=10,
            price_action_score=score - 70,
            risk_score=10,
            context_score=10,
        )
        item.features = SimpleNamespace(
            contains=lambda feature: feature in {
                FeatureType.LOW_VOLATILITY,
                FeatureType.ACCELERATION,
            }
        )
        return item


if __name__ == "__main__":
    unittest.main()
