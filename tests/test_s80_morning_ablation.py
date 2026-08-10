import csv
import json
import tempfile
import unittest
from pathlib import Path

from research.s80_morning_ablation import (
    analyze_s80_morning_filter,
    save_s80_validation_progress,
)


class S80MorningAblationTest(unittest.TestCase):
    def test_compares_qualified_rejected_and_markets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, market, code in (
                ("kospi.csv", "KOSPI", "000001"),
                ("kosdaq.csv", "KOSDAQ", "000002"),
            ):
                with (root / filename).open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["code", "market"])
                    writer.writeheader()
                    writer.writerow({"code": code, "market": market})
            trades = [
                {
                    "selection_date": "2026-01-02", "code": "000001", "score": 80,
                    "baseline_eligible": True, "qualified": True,
                    "conditions": {name: True for name in (
                        "gap_ok", "range_ok", "above_vwap", "recent_lows_stable"
                    )},
                    "baseline_net_return": .02, "stable_net_return": .03,
                },
                {
                    "selection_date": "2026-02-02", "code": "000002", "score": 90,
                    "baseline_eligible": True, "qualified": False,
                    "conditions": {
                        "gap_ok": True, "range_ok": True, "above_vwap": False,
                        "recent_lows_stable": True,
                    },
                    "baseline_net_return": -.01,
                },
            ]
            path = root / "backtest.json"
            path.write_text(json.dumps({
                "strategy_version": "test", "missing_count": 1, "trades": trades,
            }), encoding="utf-8")
            result = analyze_s80_morning_filter(path, root)
            self.assertEqual(3, result["counts"]["manifest_targets"])
            self.assertEqual(1, result["counts"]["fully_qualified"])
            self.assertAlmostEqual(.005, result["baseline_all"]["average_return"])
            self.assertAlmostEqual(.03, result["qualified_1000"]["average_return"])
            self.assertEqual(1, result["by_market"]["KOSDAQ"]["baseline"]["trades"])
            self.assertEqual(2, result["drop_one_condition"]["above_vwap"]["trades"])

    def test_validation_progress_deduplicates_and_reports_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {
                "selection_date": "2026-01-02", "code": "000001",
                "baseline_eligible": True, "qualified": True,
                "stable_net_return": .02,
            }
            paths = []
            for index in range(2):
                path = root / f"backtest-{index}.json"
                path.write_text(json.dumps({
                    "available_count": 1, "missing_count": 0, "trades": [row],
                }), encoding="utf-8")
                paths.append(path)
            result = save_s80_validation_progress(paths, root / "report")
            self.assertEqual(1, result["sample_count"])
            self.assertEqual("COLLECTING", result["status"])
            self.assertEqual(29, result["remaining_to_next_target"])
            self.assertTrue((root / "report" / "s80_validation_progress.md").exists())


if __name__ == "__main__":
    unittest.main()
