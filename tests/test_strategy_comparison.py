import unittest
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from research.strategy_comparison import _rank_summary, _simulate_trade, _summary


class StrategyComparisonTest(unittest.TestCase):
    def test_cli_can_be_invoked_from_outside_repository(self) -> None:
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, str(root / "tools" / "run_strategy_comparison.py"), "--help"],
            cwd=root.parent,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--year", result.stdout)

    def test_incomplete_unresolved_trade_is_not_counted(self) -> None:
        sessions = [
            (datetime(2026, 1, 1) + timedelta(days=index)).date().isoformat()
            for index in range(3)
        ]
        rows = [
            {"date": sessions[0], "open": 100, "high": 101, "low": 99, "close": 100},
            {"date": sessions[1], "open": 100, "high": 104, "low": 98, "close": 101},
            {"date": sessions[2], "open": 101, "high": 103, "low": 97, "close": 102},
        ]
        histories = {"000001": {"rows": rows, "index": {row["date"]: i for i, row in enumerate(rows)}}}

        self.assertIsNone(_simulate_trade("000001", sessions[0], sessions, histories))

    def test_completed_twentieth_day_trade_is_counted(self) -> None:
        sessions = [
            (datetime(2026, 1, 1) + timedelta(days=index)).date().isoformat()
            for index in range(21)
        ]
        rows = [
            {"date": day, "open": 100, "high": 104, "low": 96, "close": 101}
            for day in sessions
        ]
        histories = {"000001": {"rows": rows, "index": {row["date"]: i for i, row in enumerate(rows)}}}

        result = _simulate_trade("000001", sessions[0], sessions, histories)

        self.assertEqual(sessions[20], result["exit_date"])
        self.assertGreater(result["net_return"], 0)

    def test_summary_uses_daily_average_for_drawdown(self) -> None:
        result = _summary([
            {"signal_date": "2026-01-01", "exit_date": "2026-01-02", "net_return": 0.10},
            {"signal_date": "2026-01-01", "exit_date": "2026-01-02", "net_return": -0.10},
            {"signal_date": "2026-01-02", "exit_date": "2026-01-03", "net_return": -0.05},
        ])

        self.assertEqual(3, result["trades"])
        self.assertAlmostEqual(0.05, result["maximum_drawdown"])

    def test_rank_summary_reports_horizon_means(self) -> None:
        result = _rank_summary({
            "1-5": [{"1": 0.01, "5": 0.05}, {"1": 0.03}],
            "6-10": [],
            "11-20": [],
            "21-50": [],
        })

        self.assertAlmostEqual(0.02, result[0]["return_1d"])
        self.assertAlmostEqual(0.05, result[0]["return_5d"])
        self.assertEqual(2, result[0]["samples"])


if __name__ == "__main__":
    unittest.main()
