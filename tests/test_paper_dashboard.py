import json
import tempfile
import unittest
from pathlib import Path

from trading.paper_dashboard import (
    example_paper_dashboard,
    load_paper_dashboard,
    write_paper_dashboard,
)


class PaperDashboardTest(unittest.TestCase):
    def test_missing_projection_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = load_paper_dashboard(Path(directory) / "missing.json")

        self.assertEqual(state["environment"], "MOCK")
        self.assertFalse(state["safety"]["new_orders_allowed"])
        self.assertTrue(state["safety"]["kill_switch_active"])
        self.assertIn(
            "PAPER_ENGINE_NOT_CONFIGURED", state["safety"]["blocked_reasons"]
        )

    def test_valid_projection_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.json"
            expected = example_paper_dashboard()
            write_paper_dashboard(path, expected)
            actual = load_paper_dashboard(path)

        self.assertEqual(actual, expected)

    def test_live_environment_is_rejected_and_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.json"
            payload = example_paper_dashboard()
            payload["environment"] = "LIVE"
            path.write_text(json.dumps(payload), encoding="utf-8")
            actual = load_paper_dashboard(path)

        self.assertFalse(actual["safety"]["new_orders_allowed"])
        self.assertEqual(actual["environment"], "MOCK")
        self.assertTrue(actual["safety"]["blocked_reasons"][0].startswith(
            "PAPER_DASHBOARD_INVALID:"
        ))

    def test_sensitive_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.json"
            payload = example_paper_dashboard()
            payload["access_token"] = "must-not-leak"
            with self.assertRaises(ValueError):
                write_paper_dashboard(path, payload)


if __name__ == "__main__":
    unittest.main()
