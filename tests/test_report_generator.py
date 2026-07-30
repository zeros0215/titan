import unittest
from datetime import datetime

from analysis.analysis_result import AnalysisResult
from backtest.model.selection import Selection
from backtest.model.selection_result import SelectionResult
from decision.decision_type import DecisionType
from decision.decision_result import DecisionResult
from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade
from report.report_generator import ReportGenerator
from scoring.score_result import ScoreResult
from prediction.prediction_result import PredictionResult
from validation.decision_validation import DecisionValidation
from validation.feature_validation import FeatureValidation
from validation.prediction_validation import PredictionValidation
from validation.validation_result import ValidationResult


class ReportGeneratorTest(unittest.TestCase):
    def test_renders_precomputed_validation_values_as_markdown(self) -> None:
        validation = ValidationResult(
            total_count=4,
            success_count=3,
            fail_count=1,
            win_rate=0.75,
            average_return=0.125,
            feature_validations=[
                FeatureValidation(FeatureType.PRICE_ABOVE_MA20, 4, 3, 0.125),
            ],
            prediction_validations=[
                PredictionValidation(PredictionGrade.BUY, 4, 3, 0.125),
            ],
            decision_validations=[
                DecisionValidation(DecisionType.BUY, 4, 3, 0.125),
            ],
        )

        report = ReportGenerator().generate_markdown(validation)

        self.assertIn("# TITAN Selection Validation Report", report)
        self.assertIn("| Win rate | 75.00% |", report)
        self.assertIn(
            "| PRICE_ABOVE_MA20 | 4 | 75.00% | "
            "12.50% | 12.50% | N/A | N/A |",
            report,
        )
        self.assertIn("| BUY | 4 | 75.00% | 12.50% |", report)

    def test_renders_empty_sections_without_calculating_values(self) -> None:
        validation = ValidationResult(0, 0, 0, 0.0, 0.0, [], [], [])

        report = ReportGenerator().generate_markdown(validation)

        self.assertIn("No feature validation data.", report)
        self.assertIn("No prediction validation data.", report)
        self.assertIn("No decision validation data.", report)

    def test_renders_trade_details_when_selection_results_are_present(self) -> None:
        validation = ValidationResult(1, 1, 0, 1.0, 0.1, [], [], [])
        selection = Selection(
            AnalysisResult("000001", "Alpha", None, None, ScoreResult()),
            datetime(2026, 7, 27),
            1,
        )
        trade = SelectionResult(
            selection=selection,
            evaluation_date=datetime(2026, 8, 3),
            holding_days=5,
            selection_price=100.0,
            evaluation_price=110.0,
            return_rate=0.1,
            net_return_rate=0.09,
            benchmark_return_rate=0.03,
            excess_return_rate=0.06,
        )

        report = ReportGenerator().generate_markdown(
            validation,
            selection_results=[trade],
            success_return=0.03,
        )

        self.assertIn("## Trades", report)
        self.assertIn(
            "| 1 | 000001 | Alpha | 100.00 | 110.00 | "
            "10.00% | 9.00% | 3.00% | 6.00% | Success |",
            report,
        )

    def test_renders_precomputed_selection_facts(self) -> None:
        features = FeatureSet()
        features.add(Feature.create_enabled(FeatureType.PRICE_ABOVE_MA20, 1.0, 1.0))
        selection = Selection(
            AnalysisResult(
                code="000001",
                name="Alpha",
                indicators=None,
                features=features,
                score=ScoreResult(trend_score=15),
                prediction=PredictionResult(80, 0.8, PredictionGrade.BUY, 0.1),
                decision=DecisionResult(DecisionType.BUY, PredictionGrade.BUY, "test"),
                positive_factors=["above MA20"],
            ),
            datetime(2026, 7, 27),
            1,
        )

        report = ReportGenerator().generate_selection_markdown([selection])

        self.assertIn("# TITAN Selection Report", report)
        self.assertIn("| 1 | 000001 | Alpha | 15 | BUY | BUY |", report)
        self.assertIn("Enabled features: PRICE_ABOVE_MA20", report)

    def test_renders_empty_selection_result(self) -> None:
        report = ReportGenerator().generate_selection_markdown([])

        self.assertIn("No candidates passed the selection criteria.", report)


if __name__ == "__main__":
    unittest.main()
