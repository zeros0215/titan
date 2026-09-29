import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trading.journal import EventType, JournalEvent, SQLiteExecutionJournal
from trading.model import TradingMode
from trading.recovery import recover_execution_state


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


def append(journal, number, event_type, *, intent_id=None, payload=None):
    journal.append(JournalEvent(
        f"event-{number}", event_type, NOW, payload or {},
        intent_id=intent_id,
    ))


class ExecutionRecoveryTest(unittest.TestCase):
    def journal(self, directory):
        return SQLiteExecutionJournal(
            Path(directory) / "paper.sqlite",
            mode=TradingMode.PAPER,
            account_ref="acct_demo",
        )

    def test_empty_journal_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = recover_execution_state(
                self.journal(directory), recovery_id="boot-1"
            )

        self.assertFalse(state.safe_to_trade)
        self.assertIn("ACCOUNT_RECONCILIATION_REQUIRED", state.blocked_reasons)

    def test_uncertain_submission_is_restored_and_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            append(journal, 1, EventType.INTENT_RECORDED, intent_id="intent-1")
            append(
                journal, 2, EventType.RISK_DECIDED,
                intent_id="intent-1", payload={"approved": True},
            )
            append(
                journal, 3, EventType.ORDER_SUBMISSION_STARTED,
                intent_id="intent-1",
                payload={
                    "reserved_value": Decimal("70000"),
                    "requested_quantity": 1,
                },
            )
            append(
                journal, 4, EventType.RECONCILIATION_COMPLETED,
                payload={"ready": True, "recovery_id": "boot-1"},
            )

            state = recover_execution_state(
                self.journal(directory), recovery_id="boot-1"
            )

        self.assertFalse(state.safe_to_trade)
        self.assertEqual(Decimal("70000"), state.reserved_buying_power)
        self.assertEqual("UNKNOWN", state.open_orders[0].status.value)
        self.assertTrue(any(
            item.startswith("UNCERTAIN_SUBMISSIONS")
            for item in state.blocked_reasons
        ))

    def test_accepted_partial_fill_is_restored_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            append(journal, 1, EventType.INTENT_RECORDED, intent_id="intent-1")
            append(
                journal, 2, EventType.RISK_DECIDED,
                intent_id="intent-1", payload={"approved": True},
            )
            append(
                journal, 3, EventType.ORDER_SUBMISSION_STARTED,
                intent_id="intent-1",
                payload={
                    "reserved_value": Decimal("700000"),
                    "requested_quantity": 10,
                },
            )
            append(
                journal, 4, EventType.ORDER_ACCEPTED,
                intent_id="intent-1", payload={"broker_order_id": "order-1"},
            )
            append(
                journal, 5, EventType.FILL_RECORDED,
                intent_id="intent-1",
                payload={"fill_id": "fill-1", "quantity": 4},
            )
            append(
                journal, 6, EventType.RECONCILIATION_COMPLETED,
                payload={"ready": True, "recovery_id": "boot-1"},
            )

            state = recover_execution_state(
                self.journal(directory), recovery_id="boot-1"
            )

        self.assertTrue(state.safe_to_trade)
        self.assertEqual(4, state.open_orders[0].filled_quantity)
        self.assertEqual("PARTIALLY_FILLED", state.open_orders[0].status.value)
        self.assertEqual(frozenset({"intent-1"}), state.seen_intent_ids)

    def test_terminal_order_releases_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            append(journal, 1, EventType.INTENT_RECORDED, intent_id="intent-1")
            append(
                journal, 2, EventType.RISK_DECIDED,
                intent_id="intent-1", payload={"approved": True},
            )
            append(
                journal, 3, EventType.ORDER_SUBMISSION_STARTED,
                intent_id="intent-1",
                payload={
                    "reserved_value": Decimal("70000"),
                    "requested_quantity": 1,
                },
            )
            append(
                journal, 4, EventType.ORDER_ACCEPTED,
                intent_id="intent-1", payload={"broker_order_id": "order-1"},
            )
            append(
                journal, 5, EventType.FILL_RECORDED,
                intent_id="intent-1",
                payload={"fill_id": "fill-1", "quantity": 1},
            )
            append(
                journal, 6, EventType.RECONCILIATION_COMPLETED,
                payload={"ready": True, "recovery_id": "boot-1"},
            )

            state = recover_execution_state(journal, recovery_id="boot-1")

        self.assertTrue(state.safe_to_trade)
        self.assertEqual((), state.open_orders)
        self.assertEqual(Decimal("0"), state.reserved_buying_power)
        self.assertIn("intent-1", state.seen_intent_ids)

    def test_kill_switch_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            append(
                journal, 1, EventType.RECONCILIATION_COMPLETED,
                payload={"ready": True, "recovery_id": "boot-1"},
            )
            append(
                journal, 2, EventType.KILL_SWITCH_CHANGED,
                payload={"active": True},
            )

            state = recover_execution_state(
                self.journal(directory), recovery_id="boot-1"
            )

        self.assertTrue(state.kill_switch_active)
        self.assertFalse(state.safe_to_trade)
        self.assertIn("KILL_SWITCH_ACTIVE", state.blocked_reasons)

    def test_tampered_journal_recovers_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            append(
                journal, 1, EventType.RECONCILIATION_COMPLETED,
                payload={"ready": True, "recovery_id": "boot-1"},
            )
            with closing(sqlite3.connect(journal.path)) as connection:
                connection.execute("DROP TRIGGER journal_events_no_update")
                connection.execute(
                    "UPDATE journal_events SET payload_json='{}' WHERE sequence=1"
                )
                connection.commit()

            state = recover_execution_state(journal, recovery_id="boot-1")

        self.assertFalse(state.safe_to_trade)
        self.assertTrue(state.kill_switch_active)
        self.assertTrue(state.blocked_reasons[0].startswith(
            "JOURNAL_INTEGRITY_FAILED"
        ))

    def test_previous_process_reconciliation_does_not_unlock_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            append(
                journal, 1, EventType.RECONCILIATION_COMPLETED,
                payload={"ready": True, "recovery_id": "old-boot"},
            )

            state = recover_execution_state(
                self.journal(directory), recovery_id="new-boot"
            )

        self.assertFalse(state.safe_to_trade)
        self.assertFalse(state.reconciliation_ready)
        self.assertIn("ACCOUNT_RECONCILIATION_REQUIRED", state.blocked_reasons)

    def test_submission_without_risk_approval_is_semantic_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            append(journal, 1, EventType.INTENT_RECORDED, intent_id="intent-1")
            append(
                journal, 2, EventType.ORDER_SUBMISSION_STARTED,
                intent_id="intent-1",
                payload={
                    "reserved_value": Decimal("70000"),
                    "requested_quantity": 1,
                },
            )
            append(
                journal, 3, EventType.RECONCILIATION_COMPLETED,
                payload={"ready": True, "recovery_id": "boot-1"},
            )

            state = recover_execution_state(journal, recovery_id="boot-1")

        self.assertFalse(state.safe_to_trade)
        self.assertTrue(any(
            "submission has no approved risk decision" in reason
            for reason in state.blocked_reasons
        ))

    def test_duplicate_fill_is_semantic_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            append(journal, 1, EventType.INTENT_RECORDED, intent_id="intent-1")
            append(
                journal, 2, EventType.RISK_DECIDED,
                intent_id="intent-1", payload={"approved": True},
            )
            append(
                journal, 3, EventType.ORDER_SUBMISSION_STARTED,
                intent_id="intent-1",
                payload={
                    "reserved_value": Decimal("700000"),
                    "requested_quantity": 10,
                },
            )
            append(
                journal, 4, EventType.ORDER_ACCEPTED,
                intent_id="intent-1", payload={"broker_order_id": "order-1"},
            )
            append(
                journal, 5, EventType.FILL_RECORDED,
                intent_id="intent-1",
                payload={"fill_id": "fill-1", "quantity": 1},
            )
            append(
                journal, 6, EventType.FILL_RECORDED,
                intent_id="intent-1",
                payload={"fill_id": "fill-1", "quantity": 1},
            )
            append(
                journal, 7, EventType.RECONCILIATION_COMPLETED,
                payload={"ready": True, "recovery_id": "boot-1"},
            )

            state = recover_execution_state(journal, recovery_id="boot-1")

        self.assertFalse(state.safe_to_trade)
        self.assertTrue(any(
            "duplicate fill_id" in reason for reason in state.blocked_reasons
        ))


if __name__ == "__main__":
    unittest.main()
