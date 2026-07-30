from datetime import datetime, timedelta
import unittest

from analysis.analysis_result import AnalysisResult
from backtest.model.backtest_result import BacktestResult
from backtest.model.selection import Selection
from backtest.model.selection_result import SelectionResult
from decision.decision_result import DecisionResult
from decision.decision_type import DecisionType
from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade
from prediction.prediction_result import PredictionResult
from scoring.score_result import ScoreResult
from validation.validator import Validator
from market.context.market_context import MarketContext
from market.context.market_regime import MarketRegime
from market.context.market_trend import MarketTrend


class ValidatorTest(unittest.TestCase):
    def test_groups_performance_by_feature_prediction_and_decision(self) -> None:
        result = BacktestResult([
            self._selection_result(
                code="000001",
                return_rate=0.10,
                feature_types=[FeatureType.PRICE_ABOVE_MA20],
                grade=PredictionGrade.BUY,
                decision=DecisionType.BUY,
            ),
            self._selection_result(
                code="000002",
                return_rate=-0.02,
                feature_types=[FeatureType.PRICE_ABOVE_MA20, FeatureType.HIGH_MOMENTUM_5D],
                grade=PredictionGrade.BUY,
                decision=DecisionType.WATCH,
            ),
        ])

        validation = Validator().validate(result, success_return=0.05)

        self.assertEqual(validation.total_count, 2)
        self.assertEqual(validation.success_count, 1)
        self.assertEqual(validation.fail_count, 1)
        self.assertAlmostEqual(validation.win_rate, 0.5)
        self.assertAlmostEqual(validation.average_return, 0.04)

        by_feature = {item.feature_type: item for item in validation.feature_validations}
        self.assertEqual(by_feature[FeatureType.PRICE_ABOVE_MA20].total_count, 2)
        self.assertEqual(by_feature[FeatureType.PRICE_ABOVE_MA20].success_count, 1)
        self.assertEqual(by_feature[FeatureType.HIGH_MOMENTUM_5D].total_count, 1)

        self.assertEqual(validation.prediction_validations[0].grade, PredictionGrade.BUY)
        self.assertEqual(validation.prediction_validations[0].success_count, 1)
        self.assertEqual(len(validation.decision_validations), 2)

    def test_handles_an_empty_backtest(self) -> None:
        validation = Validator().validate(BacktestResult())

        self.assertEqual(validation.total_count, 0)
        self.assertEqual(validation.win_rate, 0.0)
        self.assertEqual(validation.feature_validations, [])

    def test_uses_net_return_and_reports_benchmark_performance(self) -> None:
        item = self._selection_result(
            code="000001",
            return_rate=0.06,
            feature_types=[FeatureType.PRICE_ABOVE_MA20],
            grade=PredictionGrade.BUY,
            decision=DecisionType.BUY,
        )
        item.net_return_rate = 0.04
        item.benchmark_return_rate = 0.03
        item.excess_return_rate = 0.01

        validation = Validator().validate(
            BacktestResult([item]),
            success_return=0.05,
        )

        self.assertEqual(validation.success_count, 0)
        self.assertAlmostEqual(validation.average_return, 0.04)
        self.assertAlmostEqual(validation.average_gross_return, 0.06)
        self.assertAlmostEqual(validation.average_net_return, 0.04)
        self.assertAlmostEqual(validation.average_benchmark_return, 0.03)
        self.assertAlmostEqual(validation.average_excess_return, 0.01)

    def test_groups_performance_by_selection_time_market_context(self) -> None:
        item = self._selection_result(
            code="000001",
            return_rate=0.06,
            feature_types=[FeatureType.PRICE_ABOVE_MA20],
            grade=PredictionGrade.BUY,
            decision=DecisionType.BUY,
        )
        item.selection.analysis.context = MarketContext(
            MarketTrend.BULL,
            MarketTrend.BULL,
            0.8,
            0.0,
            0.0,
            0.0,
            0.0,
        )
        item.benchmark_return_rate = 0.02
        item.excess_return_rate = 0.04

        validation = Validator().validate(BacktestResult([item]))

        context = validation.context_validations[0]
        self.assertEqual(context.regime, MarketRegime.BULL)
        self.assertEqual(context.total_count, 1)
        self.assertAlmostEqual(context.average_return, 0.06)
        self.assertAlmostEqual(context.average_excess_return, 0.04)
        self.assertAlmostEqual(context.average_market_strength, 0.8)
        feature = validation.feature_validations[0]
        self.assertAlmostEqual(feature.average_gross_return, 0.06)
        self.assertAlmostEqual(feature.average_benchmark_return, 0.02)
        self.assertAlmostEqual(feature.average_excess_return, 0.04)
        feature_regime = validation.feature_regime_validations[0]
        self.assertEqual(feature_regime.regime, MarketRegime.BULL)
        self.assertEqual(
            feature_regime.feature_type,
            FeatureType.PRICE_ABOVE_MA20,
        )

    def test_groups_performance_by_normalized_score_band(self) -> None:
        low = self._selection_result(
            "000001",
            0.01,
            [FeatureType.PRICE_ABOVE_MA20],
            PredictionGrade.BUY,
            DecisionType.BUY,
        )
        high = self._selection_result(
            "000002",
            0.08,
            [FeatureType.PRICE_ABOVE_MA20],
            PredictionGrade.BUY,
            DecisionType.BUY,
        )
        low.selection.analysis.score = ScoreResult(trend_score=75)
        high.selection.analysis.score = ScoreResult(
            trend_score=30,
            momentum_score=15,
            volume_score=15,
            price_action_score=15,
            risk_score=10,
            context_score=5,
        )

        validation = Validator().validate(
            BacktestResult([low, high]),
            success_return=0.03,
        )

        self.assertEqual(
            [item.label for item in validation.score_band_validations],
            ["70-79", "90-100"],
        )
        self.assertEqual(validation.score_band_validations[0].success_count, 0)
        self.assertEqual(validation.score_band_validations[1].success_count, 1)

    @staticmethod
    def _selection_result(
        code: str,
        return_rate: float,
        feature_types: list[FeatureType],
        grade: PredictionGrade,
        decision: DecisionType,
    ) -> SelectionResult:
        features = FeatureSet()
        for feature_type in feature_types:
            features.add(Feature.create_enabled(feature_type, 1.0, 1.0))

        analysis = AnalysisResult(
            code=code,
            name=code,
            indicators=None,
            features=features,
            score=ScoreResult(),
            prediction=PredictionResult(0, 0.8, grade, 0.1),
            decision=DecisionResult(decision, grade, "test"),
        )
        selected_date = datetime(2026, 1, 2)
        return SelectionResult(
            selection=Selection(analysis, selected_date, 1),
            evaluation_date=selected_date + timedelta(days=20),
            holding_days=20,
            selection_price=100.0,
            evaluation_price=100.0 * (1 + return_rate),
            return_rate=return_rate,
        )


if __name__ == "__main__":
    unittest.main()
