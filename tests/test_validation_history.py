from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from decision.decision_type import DecisionType
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade
from repository.validation_repository import ValidationRepository
from validation.aggregator import ValidationAggregator
from validation.decision_validation import DecisionValidation
from validation.feature_validation import FeatureValidation
from validation.prediction_validation import PredictionValidation
from validation.validation_record import ValidationRecord
from validation.validation_result import ValidationResult
from validation.context_validation import ContextValidation
from market.context.market_regime import MarketRegime
from validation.feature_regime_validation import FeatureRegimeValidation
from validation.score_band_validation import ScoreBandValidation


class ValidationHistoryTest(unittest.TestCase):
    def test_persists_and_aggregates_weighted_validation_history(self) -> None:
        start = datetime(2026, 1, 1)
        with TemporaryDirectory() as directory:
            repository = ValidationRepository(Path(directory))
            repository.save(self._record(start, 2, 2, 0.10))
            repository.save(self._record(start + timedelta(days=30), 1, 0, -0.10))
            records = repository.load_all()

        summary = ValidationAggregator().aggregate(records)

        self.assertEqual(summary.run_count, 2)
        self.assertEqual(summary.total_count, 3)
        self.assertEqual(summary.success_count, 2)
        self.assertAlmostEqual(summary.win_rate, 2 / 3)
        self.assertAlmostEqual(summary.average_return, 0.10 / 3)
        self.assertEqual(summary.feature_validations[0].total_count, 3)
        self.assertAlmostEqual(summary.feature_validations[0].average_return, 0.10 / 3)
        self.assertEqual(summary.context_validations[0].regime, MarketRegime.BULL)
        self.assertEqual(summary.context_validations[0].total_count, 3)
        self.assertEqual(summary.feature_regime_validations[0].total_count, 3)
        self.assertEqual(summary.score_band_validations[0].total_count, 3)

    @staticmethod
    def _record(
        selected_at: datetime,
        total_count: int,
        success_count: int,
        average_return: float,
    ) -> ValidationRecord:
        result = ValidationResult(
            total_count=total_count,
            success_count=success_count,
            fail_count=total_count - success_count,
            win_rate=success_count / total_count,
            average_return=average_return,
            feature_validations=[
                FeatureValidation(
                    FeatureType.PRICE_ABOVE_MA20,
                    total_count,
                    success_count,
                    average_return,
                ),
            ],
            prediction_validations=[
                PredictionValidation(
                    PredictionGrade.BUY,
                    total_count,
                    success_count,
                    average_return,
                ),
            ],
            decision_validations=[
                DecisionValidation(
                    DecisionType.BUY,
                    total_count,
                    success_count,
                    average_return,
                ),
            ],
            context_validations=[
                ContextValidation(
                    MarketRegime.BULL,
                    total_count,
                    success_count,
                    average_return,
                    average_return,
                )
            ],
            feature_regime_validations=[
                FeatureRegimeValidation(
                    FeatureType.PRICE_ABOVE_MA20,
                    MarketRegime.BULL,
                    total_count,
                    success_count,
                    average_return,
                    average_return,
                )
            ],
            score_band_validations=[
                ScoreBandValidation(
                    80,
                    89,
                    total_count,
                    success_count,
                    average_return,
                    average_return,
                )
            ],
        )
        return ValidationRecord(
            selected_at=selected_at,
            evaluation_date=selected_at + timedelta(days=20),
            holding_days=20,
            success_return=0.03,
            result=result,
        )


if __name__ == "__main__":
    unittest.main()
