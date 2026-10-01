import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from broker.kiwoom.paper import KiwoomPaperCredentials
from broker.kiwoom.paper_execution import KiwoomPaperApprovedSubmitter
from broker.kiwoom.paper_order import KiwoomPaperOrderDisabled, KiwoomPaperOrderGateway
from trading.coordinator import OrderCoordinator
from trading.journal import EventType, SQLiteExecutionJournal
from trading.market_rules import MarketRulesSnapshot
from trading.model import AccountSnapshot, MarketQuote, OrderIntent, OrderSide, OrderType, TradingMode
from trading.paper_operator_control import PaperOperatorControl, RELEASE_CONFIRMATION
from trading.reconciliation import ReconciliationResult
from trading.risk import RiskContext, RiskLimits, RiskManager


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


class KiwoomPaperExecutionIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.calls = []

        def handler(request):
            self.calls.append(request)
            if request.url.path == "/oauth2/token":
                return httpx.Response(200, json={
                    "token": "private-token", "expires_dt": "20300102030405",
                })
            return httpx.Response(200, json={"ord_no": "0000024", "return_code": 0})

        gateway = KiwoomPaperOrderGateway(
            KiwoomPaperCredentials("paper-key", "paper-secret"),
            submission_enabled=True,
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://mockapi.kiwoom.com",
            ),
            clock=lambda: NOW,
        )
        self.submitter = KiwoomPaperApprovedSubmitter(
            gateway,
            operator_approval_enabled=True,
            clock=lambda: NOW,
        )
        self.risk = RiskManager(RiskLimits(
            max_order_value=Decimal("200000"),
            max_position_value=Decimal("200000"),
            max_gross_exposure=Decimal("700000"),
            max_daily_loss=Decimal("100000"),
            allowed_symbols=frozenset({"005930"}),
            require_market_rules=True,
        ))
        self.intent = OrderIntent(
            "intent-1", "PAPER-CANDIDATE", "005930", OrderSide.BUY, 1,
            OrderType.MARKET, NOW, rationale="manual paper pilot",
        )
        self.context = RiskContext(
            TradingMode.PAPER,
            NOW,
            AccountSnapshot("acct_demo", NOW, Decimal("2000000"), Decimal("2000000")),
            ReconciliationResult(True, ()),
            MarketQuote("005930", NOW, Decimal("70000"), Decimal("69900"), Decimal("70100")),
            market_rules=MarketRulesSnapshot(
                "005930", "KRX", NOW, True, Decimal("70000"),
                Decimal("49000"), Decimal("91000"), Decimal("100"),
            ),
        )

    def coordinator(self, directory):
        journal = SQLiteExecutionJournal(
            Path(directory) / "orders.sqlite",
            mode=TradingMode.PAPER,
            account_ref="acct_demo",
        )
        coordinator = OrderCoordinator(
            object(), journal, self.risk,
            approved_submitter=self.submitter,
            clock=lambda: NOW,
            event_id_factory=(f"event-{number}" for number in range(1, 20)).__next__,
        )
        return coordinator, journal

    def test_operator_approved_order_preserves_journal_first_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            coordinator, journal = self.coordinator(directory)
            self.submitter.grant("intent-1", operator_ref="operator-alias")
            result = coordinator.submit(self.intent, self.context)
            events = [record.event.event_type for record in journal.records()]

        self.assertEqual("0000024", result.order.broker_order_id)
        self.assertEqual([
            EventType.INTENT_RECORDED,
            EventType.RISK_DECIDED,
            EventType.OPERATOR_ACTION,
            EventType.ORDER_SUBMISSION_STARTED,
            EventType.ORDER_ACCEPTED,
        ], events)
        self.assertEqual(2, len(self.calls))

    def test_missing_operator_approval_stops_before_submission_start(self):
        with tempfile.TemporaryDirectory() as directory:
            coordinator, journal = self.coordinator(directory)
            with self.assertRaises(KiwoomPaperOrderDisabled):
                coordinator.submit(self.intent, self.context)
            events = [record.event.event_type for record in journal.records()]

        self.assertEqual([EventType.INTENT_RECORDED, EventType.RISK_DECIDED], events)
        self.assertEqual([], self.calls)

    def test_expired_approval_is_consumed_and_never_calls_network(self):
        clock_values = iter((NOW, NOW + timedelta(minutes=1)))
        self.submitter.clock = lambda: next(clock_values)
        self.submitter.grant("intent-1", operator_ref="operator-alias")
        with tempfile.TemporaryDirectory() as directory:
            coordinator, _ = self.coordinator(directory)
            with self.assertRaisesRegex(KiwoomPaperOrderDisabled, "expired"):
                coordinator.submit(self.intent, self.context)
        self.assertEqual([], self.calls)

    def test_durable_dashboard_approval_is_consumed_once_by_coordinator(self):
        with tempfile.TemporaryDirectory() as directory:
            control = PaperOperatorControl(
                Path(directory) / "operator_control.json", clock=lambda: NOW
            )
            control.set_kill_switch(
                False, operator_ref="dashboard-operator",
                confirmation=RELEASE_CONFIRMATION,
            )
            control.decide(
                intent_id="intent-1", approved=True,
                operator_ref="dashboard-operator",
            )
            self.submitter.operator_control = control
            coordinator, journal = self.coordinator(directory)
            result = coordinator.submit(self.intent, self.context)
            remaining = control.load()["approvals"]
            operator_event = next(
                record.event for record in journal.records()
                if record.event.event_type is EventType.OPERATOR_ACTION
            )

        self.assertEqual("0000024", result.order.broker_order_id)
        self.assertEqual([], remaining)
        self.assertEqual("dashboard-operator", operator_event.payload["operator_ref"])

    def test_durable_approval_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            control = PaperOperatorControl(
                Path(directory) / "operator_control.json", clock=lambda: NOW
            )
            control.set_kill_switch(
                False, operator_ref="operator", confirmation=RELEASE_CONFIRMATION
            )
            control.decide(intent_id="intent-1", approved=True, operator_ref="operator")
            self.submitter.operator_control = control
            coordinator, _ = self.coordinator(directory)
            coordinator.submit(self.intent, self.context)
            decision = self.risk.evaluate(self.intent, self.context)
            with self.assertRaises(KiwoomPaperOrderDisabled):
                self.submitter.prepare_submission(decision, self.context)

        self.assertEqual(2, len(self.calls))


if __name__ == "__main__":
    unittest.main()
