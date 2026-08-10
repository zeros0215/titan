from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from report.report_generator import ReportGenerator
from validation.validation_result import ValidationResult
from walkforward.engine import WalkForwardEngine
from walkforward.plan import WalkForwardPlan
from repository.walk_forward_repository import WalkForwardRepository


class WalkForwardTest(unittest.TestCase):
    def test_builds_expanding_year_folds_without_overlap(self) -> None:
        plan = WalkForwardPlan.expanding_years(2022, 2023, 2025)

        self.assertEqual(len(plan.folds), 3)
        self.assertEqual(plan.folds[0].training_end.year, 2022)
        self.assertEqual(plan.folds[0].test_start.year, 2023)
        self.assertEqual(plan.folds[2].training_start.year, 2022)
        self.assertEqual(plan.folds[2].training_end.year, 2024)
        self.assertEqual(plan.folds[2].test_start.year, 2025)

    def test_weekly_dates_start_on_first_weekday(self) -> None:
        fold = WalkForwardPlan.expanding_years(2022, 2023, 2023).folds[0]
        dates = fold.selection_dates(1, interval_days=7)

        self.assertGreater(len(dates), 50)
        self.assertTrue(all(item.weekday() < 5 for item in dates))

    def test_daily_dates_exclude_weekends(self) -> None:
        fold = WalkForwardPlan.expanding_years(2022, 2023, 2023).folds[0]
        dates = fold.selection_dates(1, interval_days=1)

        self.assertTrue(all(item.weekday() < 5 for item in dates))
        self.assertGreater(len(dates), 250)

    def test_replays_frozen_strategy_and_reports_incomplete_universe(self) -> None:
        selection_runner = _SelectionRunner()
        validation_runner = _ValidationRunner()
        result = WalkForwardEngine(
            selection_runner,
            validation_runner,
        ).run(
            WalkForwardPlan.expanding_years(2022, 2023, 2023),
            holding_days=20,
            interval_months=6,
        )

        fold = result.folds[0]
        self.assertTrue(result.strategy_frozen)
        self.assertEqual(fold.attempted_dates, 2)
        self.assertEqual(fold.completed_dates, 2)
        self.assertEqual(fold.total_count, 4)
        self.assertAlmostEqual(fold.win_rate, 0.5)
        self.assertTrue(
            all(
                call["as_of"].year == 2023
                for call in validation_runner.calls
            )
        )

        report = ReportGenerator().generate_walk_forward_markdown(result)
        self.assertIn("TITAN Walk-Forward Validation Report", report)
        self.assertIn("survivorship bias may remain", report)
        with TemporaryDirectory() as directory:
            path = WalkForwardRepository(Path(directory)).save(result)
            self.assertTrue(path.exists())

    def test_rejects_invalid_plan_boundaries(self) -> None:
        with self.assertRaisesRegex(ValueError, "before"):
            WalkForwardPlan.expanding_years(2023, 2023, 2024)

    def test_records_candidate_version_and_config_hash(self) -> None:
        result = WalkForwardEngine(
            _SelectionRunner(),
            _ValidationRunner(),
            strategy_version="1.1.0",
            strategy_config_hash="abc123",
        ).run(
            WalkForwardPlan.expanding_years(2022, 2023, 2023),
            interval_months=12,
        )

        self.assertEqual("1.1.0", result.strategy_version)
        self.assertEqual("abc123", result.strategy_config_hash)


class _SelectionRunner:
    def select(self, selected_at, top_n):
        return SimpleNamespace(
            selections=[object(), object()],
            universe_snapshot=SimpleNamespace(
                coverage=SimpleNamespace(value="UNKNOWN")
            ),
        )


class _ValidationRunner:
    def __init__(self) -> None:
        self.calls = []

    def run_horizons(self, **kwargs):
        self.calls.append(kwargs)
        validation = ValidationResult(
            total_count=2,
            success_count=1,
            fail_count=1,
            win_rate=0.5,
            average_return=0.02,
            feature_validations=[],
            prediction_validations=[],
            decision_validations=[],
            average_gross_return=0.025,
            average_net_return=0.02,
            average_benchmark_return=0.01,
            average_excess_return=0.01,
        )
        return {
            kwargs["holding_days"][0]: SimpleNamespace(validation=validation)
        }


if __name__ == "__main__":
    unittest.main()
