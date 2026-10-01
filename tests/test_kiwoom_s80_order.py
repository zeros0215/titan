import tempfile
import unittest
from pathlib import Path

from trading.kiwoom_s80_order import (
    submit_s80_paper_candidate, submit_s80_paper_exit,
)
from trading.paper_dashboard import example_paper_dashboard, write_paper_dashboard


class KiwoomS80OrderTest(unittest.TestCase):
    def test_unknown_candidate_stops_before_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dashboard = root / "dashboard.json"
            write_paper_dashboard(dashboard, example_paper_dashboard())
            with self.assertRaisesRegex(ValueError, "eligible S80 candidate"):
                submit_s80_paper_candidate(
                    "s80-unknown",
                    dashboard_path=dashboard,
                    control_path=root / "control.json",
                    journal_path=root / "orders.sqlite",
                )

    def test_disabled_candidate_stops_before_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dashboard = root / "dashboard.json"
            state = example_paper_dashboard()
            state["candidates"] = [{
                "intent_id": "s80-2026-09-29-005930",
                "code": "005930",
                "eligible": True,
                "approval_enabled": False,
            }]
            write_paper_dashboard(dashboard, state)
            with self.assertRaisesRegex(ValueError, "submission is disabled"):
                submit_s80_paper_candidate(
                    "s80-2026-09-29-005930",
                    dashboard_path=dashboard,
                    control_path=root / "control.json",
                    journal_path=root / "orders.sqlite",
                )

    def test_unknown_exit_stops_before_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dashboard = root / "dashboard.json"
            write_paper_dashboard(dashboard, example_paper_dashboard())
            with self.assertRaisesRegex(ValueError, "exit signal"):
                submit_s80_paper_exit(
                    "s80-exit-unknown",
                    dashboard_path=dashboard,
                    control_path=root / "control.json",
                    journal_path=root / "orders.sqlite",
                )

    def test_unknown_manual_exit_stops_before_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dashboard = root / "dashboard.json"
            write_paper_dashboard(dashboard, example_paper_dashboard())
            with self.assertRaisesRegex(ValueError, "manual exit"):
                submit_s80_paper_exit(
                    "s80-manual-exit-unknown",
                    dashboard_path=dashboard,
                    control_path=root / "control.json",
                    journal_path=root / "orders.sqlite",
                    manual=True,
                )


if __name__ == "__main__":
    unittest.main()
