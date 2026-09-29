import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trading.coordinator import (
    OrderCoordinator,
    PostSubmissionJournalError,
    SubmissionUncertainError,
)
from trading.journal import EventType, SQLiteExecutionJournal
from trading.model import (
    AccountSnapshot,
    MarketQuote,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingMode,
)
from trading.reconciliation import ReconciliationResult
from trading.recovery import recover_execution_state
from trading.risk import RiskContext, RiskLimits, RiskManager, RiskReason
from trading.simulated_broker import (
    SimulatedBrokerConfig,
    SimulatedBrokerTimeout,
    SimulatedExecutionBroker,
    SimulatedScenario,
)


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


class FailingJournal:
    def __init__(self, delegate, fail_on_append: int):
        self.delegate = delegate
        self.fail_on_append = fail_on_append
        self.append_count = 0

    def append(self, event):
        self.append_count += 1
        if self.append_count == self.fail_on_append:
            raise OSError("simulated durable write failure")
        return self.delegate.append(event)

    def has_intent(self, intent_id):
        return self.delegate.has_intent(intent_id)

    def has_fill(self, fill_id):
        return self.delegate.has_fill(fill_id)

    def verify(self):
        return self.delegate.verify()


class OrderCoordinatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.account = AccountSnapshot(
            "acct_demo", NOW, Decimal("2000000"), Decimal("2000000")
        )
        self.quote = MarketQuote(
            "005930", NOW, Decimal("70000"), Decimal("69900"), Decimal("70100")
        )
        self.risk = RiskManager(RiskLimits(
            max_order_value=Decimal("200000"),
            max_position_value=Decimal("200000"),
            max_gross_exposure=Decimal("700000"),
            max_daily_loss=Decimal("100000"),
            max_open_orders=7,
            allowed_symbols=frozenset({"005930"}),
        ))

    def intent(self, intent_id="intent-1", quantity=1):
        return OrderIntent(
            intent_id,
            "V1.3-S80-N7-TP5-SL10-CANDIDATE",
            "005930",
            OrderSide.BUY,
            quantity,
            OrderType.MARKET,
            NOW,
            rationale="S80 paper entry",
        )

    def context(self, **changes):
        values = {
            "mode": TradingMode.PAPER,
            "now": NOW,
            "account": self.account,
            "reconciliation": ReconciliationResult(True, ()),
            "quote": self.quote,
        }
        values.update(changes)
        return RiskContext(**values)

    def journal(self, directory):
        return SQLiteExecutionJournal(
            Path(directory) / "orders.sqlite",
            mode=TradingMode.PAPER,
            account_ref="acct_demo",
        )

    def coordinator(self, broker, journal):
        numbers = iter(range(1, 100))
        return OrderCoordinator(
            broker,
            journal,
            self.risk,
            clock=lambda: NOW,
            event_id_factory=lambda: f"event-{next(numbers)}",
        )

    def broker(self, scenario=SimulatedScenario.FULL_FILL):
        return SimulatedExecutionBroker(
            self.account,
            {"005930": Decimal("70100")},
            config=SimulatedBrokerConfig(scenario),
        )

    def test_full_fill_is_journaled_before_and_after_submission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            broker = self.broker()
            result = self.coordinator(broker, journal).submit(
                self.intent(), self.context()
            )
            records = journal.records()

        self.assertEqual(OrderStatus.FILLED, result.order.status)
        self.assertEqual(1, len(result.fills))
        self.assertEqual(1, broker.submit_count)
        self.assertEqual(
            [
                EventType.INTENT_RECORDED,
                EventType.RISK_DECIDED,
                EventType.ORDER_SUBMISSION_STARTED,
                EventType.ORDER_ACCEPTED,
                EventType.FILL_RECORDED,
            ],
            [record.event.event_type for record in records],
        )

    def test_rejected_risk_never_calls_broker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            broker = self.broker()
            result = self.coordinator(broker, journal).submit(
                self.intent(), self.context(kill_switch_active=True)
            )

        self.assertFalse(result.decision.approved)
        self.assertIn(RiskReason.KILL_SWITCH_ACTIVE, result.decision.reasons)
        self.assertEqual(0, broker.submit_count)
        self.assertIsNone(result.order)

    def test_partial_fill_is_recorded_once_and_remains_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            broker = self.broker(SimulatedScenario.PARTIAL_FILL)
            coordinator = self.coordinator(broker, journal)
            result = coordinator.submit(self.intent(quantity=2), self.context())
            duplicate_recorded = coordinator.record_fill(
                self.intent().intent_id, result.fills[0]
            )
            recovered = recover_execution_state(journal, recovery_id="restart-1")

        self.assertEqual(OrderStatus.PARTIALLY_FILLED, result.order.status)
        self.assertEqual(1, result.order.filled_quantity)
        self.assertFalse(duplicate_recorded)
        self.assertEqual(1, recovered.open_orders[0].filled_quantity)
        self.assertEqual(OrderStatus.PARTIALLY_FILLED, recovered.open_orders[0].status)

    def test_broker_rejection_is_terminal_and_durably_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            broker = self.broker(SimulatedScenario.REJECT)
            result = self.coordinator(broker, journal).submit(
                self.intent(), self.context()
            )
            recovered = recover_execution_state(journal, recovery_id="restart-1")

        self.assertEqual(OrderStatus.REJECTED, result.order.status)
        self.assertEqual((), recovered.open_orders)

    def test_timeout_after_acceptance_is_not_retried_and_recovers_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            broker = self.broker(SimulatedScenario.TIMEOUT_AFTER_ACCEPT)
            coordinator = self.coordinator(broker, journal)
            with self.assertRaises(SubmissionUncertainError) as raised:
                coordinator.submit(self.intent(), self.context())
            recovered = recover_execution_state(journal, recovery_id="restart-1")

        self.assertIsInstance(raised.exception.__cause__, SimulatedBrokerTimeout)
        self.assertEqual(1, broker.submit_count)
        self.assertEqual(OrderStatus.UNKNOWN, recovered.open_orders[0].status)
        self.assertTrue(any(
            reason.startswith("UNCERTAIN_SUBMISSIONS")
            for reason in recovered.blocked_reasons
        ))

    def test_journal_failure_before_submission_prevents_broker_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = self.broker()
            journal = FailingJournal(self.journal(directory), fail_on_append=3)
            with self.assertRaises(OSError):
                self.coordinator(broker, journal).submit(
                    self.intent(), self.context()
                )

        self.assertEqual(0, broker.submit_count)

    def test_journal_failure_after_broker_response_requires_kill_switch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = self.broker()
            journal = FailingJournal(self.journal(directory), fail_on_append=4)
            with self.assertRaises(PostSubmissionJournalError):
                self.coordinator(broker, journal).submit(
                    self.intent(), self.context()
                )

        self.assertEqual(1, broker.submit_count)

    def test_duplicate_intent_is_never_resubmitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = self.journal(directory)
            broker = self.broker()
            coordinator = self.coordinator(broker, journal)
            coordinator.submit(self.intent(), self.context())
            with self.assertRaisesRegex(ValueError, "already recorded"):
                coordinator.submit(self.intent(), self.context())

        self.assertEqual(1, broker.submit_count)

    def test_cancel_race_can_fill_instead_of_cancel(self) -> None:
        broker = self.broker(SimulatedScenario.CANCEL_RACE_FILL)
        request = self.risk.evaluate(self.intent(), self.context()).request
        order = broker.submit_order(request)
        result = broker.cancel_order(order.broker_order_id)

        self.assertEqual(OrderStatus.FILLED, result.status)
        self.assertEqual(1, len(broker.fills_for_order(result.broker_order_id)))


if __name__ == "__main__":
    unittest.main()
