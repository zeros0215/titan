import tempfile
import unittest
from pathlib import Path

from trading.paper_automation_control import (
    PaperAutomationControl, select_automatic_action,
)


class PaperAutomationControlTest(unittest.TestCase):
    def test_missing_or_corrupt_state_is_off(self):
        with tempfile.TemporaryDirectory() as directory:
            control = PaperAutomationControl(Path(directory) / "automation.json")
            self.assertEqual("OFF", control.load()["mode"])

    def test_each_active_mode_requires_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            control = PaperAutomationControl(Path(directory) / "automation.json")
            with self.assertRaisesRegex(ValueError, "exact confirmation"):
                control.set_mode("AUTO_TRADE", operator_ref="tester")
            state = control.set_mode(
                "AUTO_TRADE", operator_ref="tester",
                confirmation="ENABLE_PAPER_AUTO_TRADE",
            )
            self.assertEqual("AUTO_TRADE", state["mode"])
            self.assertEqual("OFF", control.set_mode(
                "OFF", operator_ref="tester"
            )["mode"])

    def test_auto_trade_prioritizes_exit_and_buy_window_closes_at_ten(self):
        state = {
            "positions": [{
                "exit_approval_enabled": True, "exit_intent_id": "sell-1",
            }],
            "candidates": [{
                "eligible": True, "approval_enabled": True,
                "intent_id": "buy-1",
            }],
        }
        self.assertEqual(
            ("SELL", "sell-1"),
            select_automatic_action(state, "AUTO_TRADE", hour=9, minute=5),
        )
        state["positions"] = []
        self.assertEqual(
            ("BUY", "buy-1"),
            select_automatic_action(state, "AUTO_BUY", hour=10, minute=0),
        )
        self.assertIsNone(
            select_automatic_action(state, "AUTO_BUY", hour=10, minute=1)
        )


if __name__ == "__main__":
    unittest.main()
