import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from monitoring.engine import MonitoringEngine
from monitoring.model import MonitorStatus
from monitoring.policy import MonitoringPolicy
from monitoring.report import generate_monitoring_markdown
from repository.monitoring_repository import MonitoringRepository
from validation.aggregator import ValidationAggregator
from validation.validation_record import ValidationRecord
from validation.validation_result import ValidationResult


class MonitoringEngineTest(unittest.TestCase):
    def setUp(self):
        self.policy = MonitoringPolicy(
            recent_run_count=6,
            minimum_sample_size=30,
        )
        self.engine = MonitoringEngine(ValidationAggregator(), self.policy)

    def test_insufficient_samples_do_not_raise_false_alert(self):
        snapshot = self.engine.build([
            self._record(0, 20, 10, 0.0, 20),
        ])

        self.assertEqual(MonitorStatus.NORMAL, snapshot.status)
        self.assertEqual("INSUFFICIENT_DATA", snapshot.data_state)
        self.assertIn("최소 30개", snapshot.reasons[0])

    def test_severe_recent_deterioration_raises_alert(self):
        records = []
        for index in range(6):
            records.append(self._record(index, 5, 4, 0.04, 20))
        for index in range(6, 12):
            records.append(self._record(index, 5, 1, -0.04, 20))

        snapshot = self.engine.build(records)

        self.assertEqual(MonitorStatus.ALERT, snapshot.status)
        self.assertEqual("READY", snapshot.data_state)
        horizon = snapshot.horizons[0]
        self.assertAlmostEqual(-0.6, horizon.win_rate_delta)
        self.assertAlmostEqual(-0.08, horizon.excess_return_delta)
        self.assertTrue(horizon.reasons)

    def test_horizons_are_assessed_independently(self):
        records = []
        for index in range(12):
            records.append(self._record(index, 5, 4, 0.03, 5))
            records.append(self._record(index, 5, 4, 0.03, 40))

        snapshot = self.engine.build(records)

        self.assertEqual([5, 40], [item.holding_days for item in snapshot.horizons])
        self.assertTrue(all(
            item.status == MonitorStatus.NORMAL
            for item in snapshot.horizons
        ))

    def test_report_and_snapshot_are_persistable(self):
        snapshot = self.engine.build(
            [],
            quality_records=[{
                "total_count": 10,
                "valid_count": 9,
                "warning_count": 2,
                "excluded_count": 1,
            }],
        )
        report = generate_monitoring_markdown(snapshot)
        with tempfile.TemporaryDirectory() as temporary:
            path = MonitoringRepository(Path(temporary)).save(snapshot)

            self.assertTrue(path.exists())
            self.assertIn("종합 상태", report)
            self.assertIn("INSUFFICIENT_DATA", report)
            self.assertIn("10.00%", report)

    @staticmethod
    def _record(index, total, success, excess, holding_days):
        selected_at = datetime(2025, 1, 1) + timedelta(days=index)
        result = ValidationResult(
            total_count=total,
            success_count=success,
            fail_count=total - success,
            win_rate=success / total,
            average_return=excess,
            feature_validations=[],
            prediction_validations=[],
            decision_validations=[],
            average_gross_return=excess,
            average_net_return=excess,
            average_benchmark_return=0.0,
            average_excess_return=excess,
        )
        return ValidationRecord(
            selected_at=selected_at,
            evaluation_date=selected_at + timedelta(days=holding_days),
            holding_days=holding_days,
            success_return=0.03,
            result=result,
        )


if __name__ == "__main__":
    unittest.main()
