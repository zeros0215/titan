import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

from report.exporter import ValidationExporter
from validation.decision_validation import DecisionValidation
from validation.feature_validation import FeatureValidation
from validation.prediction_validation import PredictionValidation
from validation.validation_record import ValidationRecord
from validation.validation_result import ValidationResult
from decision.decision_type import DecisionType
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade


class ValidationExporterTest(unittest.TestCase):
    def test_exports_validation_summary_to_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "validation.csv"
            exporter = ValidationExporter()
            record = ValidationRecord(
                selected_at=datetime(2026, 7, 27),
                evaluation_date=datetime(2026, 8, 3),
                holding_days=5,
                success_return=0.03,
                result=ValidationResult(
                    total_count=4,
                    success_count=4,
                    fail_count=0,
                    win_rate=1.0,
                    average_return=0.0638,
                    feature_validations=[FeatureValidation(FeatureType.BREAKOUT_60, 4, 4, 0.0638)],
                    prediction_validations=[PredictionValidation(PredictionGrade.BUY, 4, 4, 0.0638)],
                    decision_validations=[DecisionValidation(DecisionType.BUY, 4, 4, 0.0638)],
                ),
            )

            saved_path = exporter.export([record], output_path, fmt="csv")

            self.assertTrue(saved_path.exists())
            frame = pd.read_csv(saved_path)
            self.assertEqual(frame.loc[0, "total_count"], 4)
            self.assertEqual(frame.loc[0, "win_rate"], 1.0)
            self.assertEqual(frame.loc[0, "average_return"], 0.0638)

    def test_exports_report_package_with_markdown_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            package_dir = Path(tmp_dir) / "package"
            exporter = ValidationExporter()
            record = ValidationRecord(
                selected_at=datetime(2026, 7, 27),
                evaluation_date=datetime(2026, 8, 3),
                holding_days=5,
                success_return=0.03,
                result=ValidationResult(
                    total_count=4,
                    success_count=4,
                    fail_count=0,
                    win_rate=1.0,
                    average_return=0.0638,
                    feature_validations=[FeatureValidation(FeatureType.BREAKOUT_60, 4, 4, 0.0638)],
                    prediction_validations=[PredictionValidation(PredictionGrade.BUY, 4, 4, 0.0638)],
                    decision_validations=[DecisionValidation(DecisionType.BUY, 4, 4, 0.0638)],
                ),
            )

            exported_dir = exporter.export_package([record], package_dir, fmt="csv")

            self.assertTrue(exported_dir.exists())
            self.assertTrue((exported_dir / "validation_report.md").exists())
            self.assertTrue((exported_dir / "validation_summary.csv").exists())
            self.assertTrue((exported_dir / "context_performance.csv").exists())
            self.assertTrue((exported_dir / "feature_performance.csv").exists())
            self.assertTrue(
                (exported_dir / "feature_regime_performance.csv").exists()
            )
            self.assertTrue(
                (exported_dir / "score_band_performance.csv").exists()
            )


if __name__ == "__main__":
    unittest.main()
