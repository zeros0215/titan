import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading.paper_operator_control import PaperOperatorControl, RELEASE_CONFIRMATION


NOW = datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc)


class PaperOperatorControlTest(unittest.TestCase):
    def control(self, directory):
        return PaperOperatorControl(
            Path(directory) / "operator_control.json", clock=lambda: NOW
        )

    def test_missing_and_corrupt_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            control = self.control(directory)
            self.assertTrue(control.load()["kill_switch_active"])
            control.path.write_text("not-json", encoding="utf-8")
            self.assertTrue(control.load()["kill_switch_active"])

    def test_release_requires_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            control = self.control(directory)
            with self.assertRaisesRegex(ValueError, "confirmation"):
                control.set_kill_switch(False, operator_ref="operator")
            state = control.set_kill_switch(
                False, operator_ref="operator", confirmation=RELEASE_CONFIRMATION
            )
        self.assertFalse(state["kill_switch_active"])

    def test_approval_requires_released_kill_switch_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            control = self.control(directory)
            with self.assertRaisesRegex(ValueError, "kill switch"):
                control.decide(intent_id="intent-1", approved=True, operator_ref="operator")
            control.set_kill_switch(
                False, operator_ref="operator", confirmation=RELEASE_CONFIRMATION
            )
            with self.assertRaisesRegex(ValueError, "five minutes"):
                control.decide(
                    intent_id="intent-1", approved=True, operator_ref="operator",
                    ttl=timedelta(minutes=6),
                )
            state = control.decide(
                intent_id="intent-1", approved=True, operator_ref="operator"
            )
        self.assertEqual("APPROVED", state["approvals"][0]["decision"])

    def test_activating_kill_switch_revokes_all_approvals(self):
        with tempfile.TemporaryDirectory() as directory:
            control = self.control(directory)
            control.set_kill_switch(
                False, operator_ref="operator", confirmation=RELEASE_CONFIRMATION
            )
            control.decide(intent_id="intent-1", approved=True, operator_ref="operator")
            state = control.set_kill_switch(True, operator_ref="operator")
            stored = json.loads(control.path.read_text(encoding="utf-8"))
        self.assertEqual([], state["approvals"])
        self.assertEqual([], stored["approvals"])

    def test_valid_approval_can_be_consumed_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            control = self.control(directory)
            control.set_kill_switch(
                False, operator_ref="operator", confirmation=RELEASE_CONFIRMATION
            )
            control.decide(intent_id="intent-1", approved=True, operator_ref="operator")
            approval = control.consume_approval("intent-1")
            with self.assertRaisesRegex(ValueError, "required"):
                control.consume_approval("intent-1")
        self.assertEqual("APPROVED", approval["decision"])

    def test_rejected_decision_is_consumed_but_never_authorizes(self):
        with tempfile.TemporaryDirectory() as directory:
            control = self.control(directory)
            control.decide(intent_id="intent-1", approved=False, operator_ref="operator")
            control.set_kill_switch(
                False, operator_ref="operator", confirmation=RELEASE_CONFIRMATION
            )
            with self.assertRaisesRegex(ValueError, "rejected"):
                control.consume_approval("intent-1")
            with self.assertRaisesRegex(ValueError, "required"):
                control.consume_approval("intent-1")


if __name__ == "__main__":
    unittest.main()
