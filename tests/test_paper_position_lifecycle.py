import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
import tempfile
from pathlib import Path
from uuid import uuid4

from trading.paper_position_lifecycle import (
    exit_signal, holding_sessions, managed_s80_symbols,
)
from trading.journal import EventType, JournalEvent, SQLiteExecutionJournal
from trading.model import TradingMode


class PaperPositionLifecycleTest(unittest.TestCase):
    def test_holding_sessions_excludes_entry_day_and_weekend(self):
        self.assertEqual(1, holding_sessions(date(2026, 9, 25), date(2026, 9, 28)))
        self.assertEqual(0, holding_sessions(date(2026, 9, 28), date(2026, 9, 28)))

    def test_stop_has_priority_over_target_and_time(self):
        self.assertEqual("STOP_LOSS", exit_signal(Decimal("100"), Decimal("90"), 20))
        self.assertEqual("TAKE_PROFIT", exit_signal(Decimal("100"), Decimal("105"), 20))
        self.assertEqual("MAX_HOLDING", exit_signal(Decimal("100"), Decimal("101"), 20))
        self.assertIsNone(exit_signal(Decimal("100"), Decimal("104"), 19))

    def test_journal_ownership_requires_accepted_buy_and_ends_on_sell(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = SQLiteExecutionJournal(
                Path(directory) / "orders.sqlite",
                mode=TradingMode.PAPER,
                account_ref="kiwoom_paper",
            )
            self._intent(journal, "buy", "BUY")
            self.assertEqual(set(), managed_s80_symbols(journal))
            self._accepted(journal, "buy")
            self.assertEqual({"005930"}, managed_s80_symbols(journal))
            self._intent(journal, "sell", "SELL")
            self._accepted(journal, "sell")
            self.assertEqual(set(), managed_s80_symbols(journal))

    @staticmethod
    def _intent(journal, intent_id, side):
        journal.append(JournalEvent(
            uuid4().hex, EventType.INTENT_RECORDED,
            datetime.now(timezone.utc), {
                "strategy_version": "V1.3-S80-N7-TP5-SL10-CANDIDATE",
                "symbol": "005930", "side": side, "quantity": 1,
            }, intent_id=intent_id,
        ))

    @staticmethod
    def _accepted(journal, intent_id):
        journal.append(JournalEvent(
            uuid4().hex, EventType.ORDER_ACCEPTED,
            datetime.now(timezone.utc), {"broker_order_id": uuid4().hex},
            intent_id=intent_id,
        ))


if __name__ == "__main__":
    unittest.main()
