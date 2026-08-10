import unittest
from dataclasses import replace

from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from scoring.policies.trend_policy import TrendPolicy
from scoring.score_constants import ScoreConstants
from scoring.score_result import ScoreResult
from scoring.score_engine import ScoreEngine
from config.selection_criteria import SELECTION_CRITERIA


class ScoreResultTest(unittest.TestCase):
    def test_total_score_sums_category_scores(self) -> None:
        result = ScoreResult(
            trend_score=30,
            momentum_score=15,
            volume_score=15,
            price_action_score=15,
            risk_score=15,
            context_score=10,
        )

        self.assertEqual(result.total_score, 100)
        self.assertEqual(result.normalized_score, 100)

    def test_score_budget_is_100(self) -> None:
        self.assertEqual(ScoreConstants.MAX_SCORE, 100)

    def test_research_category_weight_rescales_category_budget(self) -> None:
        engine = ScoreEngine(replace(
            SELECTION_CRITERIA,
            trend_weight=35,
            risk_weight=10,
        ))

        self.assertEqual(35, engine._weighted(30, 30, "trend_weight"))
        self.assertEqual(10, engine._weighted(15, 15, "risk_weight"))

    def test_enabled_trend_conditions_receive_their_configured_budget(self) -> None:
        features = FeatureSet()
        for feature_type in (
            FeatureType.PRICE_ABOVE_MA20,
            FeatureType.PRICE_ABOVE_MA60,
            FeatureType.MA5_ABOVE_MA20,
            FeatureType.MA20_ABOVE_MA60,
        ):
            features.add(Feature.create_enabled(feature_type, 0.01, 0.01))

        score = TrendPolicy().calculate(features)

        self.assertEqual(score, 30)


if __name__ == "__main__":
    unittest.main()
