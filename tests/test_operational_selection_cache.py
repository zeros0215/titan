import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.kis_dashboard_server import _find_cached_operational_selection


class OperationalSelectionCacheTest(unittest.TestCase):
    def test_reuses_pass_for_same_date_and_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "pass.json").write_text(
                json.dumps({
                    "as_of": "2026-07-30T00:00:00",
                    "status": "PASS",
                    "strategy_version":
                        "V1.3-S80-N7-TP5-SL10-CANDIDATE",
                    "selection_count": 1,
                }),
                encoding="utf-8",
            )
            cached = _find_cached_operational_selection(
                run_dir, date(2026, 7, 30)
            )

        self.assertIsNotNone(cached)
        self.assertEqual(cached["selection_count"], 1)

    def test_does_not_reuse_failed_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "fail.json").write_text(
                json.dumps({
                    "as_of": "2026-07-31T00:00:00",
                    "status": "FAIL",
                    "strategy_version":
                        "V1.3-S80-N7-TP5-SL10-CANDIDATE",
                }),
                encoding="utf-8",
            )
            cached = _find_cached_operational_selection(
                run_dir, date(2026, 7, 31)
            )

        self.assertIsNone(cached)
