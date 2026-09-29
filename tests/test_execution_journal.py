import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trading.journal import (
    DuplicateIntentError,
    EventType,
    JournalBindingError,
    JournalEvent,
    SQLiteExecutionJournal,
)
from trading.model import TradingMode


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


def event(event_id, event_type, *, intent_id=None, payload=None):
    return JournalEvent(
        event_id, event_type, NOW, payload or {}, intent_id=intent_id
    )


class ExecutionJournalTest(unittest.TestCase):
    def test_appends_and_verifies_hash_chain_after_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.sqlite"
            journal = SQLiteExecutionJournal(
                path, mode=TradingMode.PAPER, account_ref="acct_demo"
            )
            first = journal.append(event(
                "event-1", EventType.INTENT_RECORDED,
                intent_id="intent-1",
                payload={"price": Decimal("70000")},
            ))
            second = journal.append(event(
                "event-2", EventType.RISK_DECIDED,
                intent_id="intent-1", payload={"approved": True},
            ))

            reopened = SQLiteExecutionJournal(
                path, mode=TradingMode.PAPER, account_ref="acct_demo"
            )
            result = reopened.verify()
            has_intent = reopened.has_intent("intent-1")

        self.assertTrue(result.valid)
        self.assertEqual(2, result.event_count)
        self.assertEqual(first.event_hash, second.previous_hash)
        self.assertTrue(has_intent)

    def test_duplicate_intent_is_rejected_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = SQLiteExecutionJournal(
                Path(directory) / "paper.sqlite",
                mode=TradingMode.PAPER,
                account_ref="acct_demo",
            )
            journal.append(event(
                "event-1", EventType.INTENT_RECORDED,
                intent_id="intent-1",
            ))

            with self.assertRaises(DuplicateIntentError):
                journal.append(event(
                    "event-2", EventType.INTENT_RECORDED,
                    intent_id="intent-1",
                ))

            self.assertEqual(1, journal.verify().event_count)

    def test_has_fill_supports_idempotent_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = SQLiteExecutionJournal(
                Path(directory) / "fills.sqlite",
                mode=TradingMode.PAPER,
                account_ref="acct_demo",
            )
            journal.append(event(
                "fill-event", EventType.FILL_RECORDED,
                intent_id="intent-1",
                payload={"fill_id": "fill-1", "quantity": 1},
            ))

            self.assertTrue(journal.has_fill("fill-1"))
            self.assertFalse(journal.has_fill("fill-2"))

    def test_database_rejects_update_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.sqlite"
            journal = SQLiteExecutionJournal(
                path, mode=TradingMode.PAPER, account_ref="acct_demo"
            )
            journal.append(event(
                "event-1", EventType.INTENT_RECORDED,
                intent_id="intent-1",
            ))

            with closing(sqlite3.connect(path)) as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "UPDATE journal_events SET payload_json='{}'"
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("DELETE FROM journal_events")

    def test_hash_verification_detects_external_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.sqlite"
            journal = SQLiteExecutionJournal(
                path, mode=TradingMode.PAPER, account_ref="acct_demo"
            )
            journal.append(event(
                "event-1", EventType.INTENT_RECORDED,
                intent_id="intent-1", payload={"symbol": "005930"},
            ))
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("DROP TRIGGER journal_events_no_update")
                connection.execute(
                    "UPDATE journal_events SET payload_json=? WHERE sequence=1",
                    (json.dumps({"symbol": "000660"}),),
                )
                connection.commit()

            result = journal.verify()

        self.assertFalse(result.valid)
        self.assertIn("event hash mismatch", result.error)

    def test_reopen_with_different_environment_or_account_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite"
            SQLiteExecutionJournal(
                path, mode=TradingMode.PAPER, account_ref="acct_demo"
            )

            with self.assertRaises(JournalBindingError):
                SQLiteExecutionJournal(
                    path, mode=TradingMode.LIVE, account_ref="acct_demo"
                )
            with self.assertRaises(JournalBindingError):
                SQLiteExecutionJournal(
                    path, mode=TradingMode.PAPER, account_ref="acct_other"
                )

    def test_rejects_secrets_floats_and_raw_account_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                SQLiteExecutionJournal(
                    Path(directory) / "raw.sqlite",
                    mode=TradingMode.PAPER,
                    account_ref="1234567890",
                )
            journal = SQLiteExecutionJournal(
                Path(directory) / "safe.sqlite",
                mode=TradingMode.PAPER,
                account_ref="acct_demo",
            )
            with self.assertRaises(ValueError):
                journal.append(event(
                    "secret", EventType.OPERATOR_ACTION,
                    payload={"nested": {"kiwoom_app_secret": "do-not-store"}},
                ))
            with self.assertRaises(ValueError):
                journal.append(event(
                    "float", EventType.OPERATOR_ACTION,
                    payload={"price": 1.5},
                ))


if __name__ == "__main__":
    unittest.main()
