import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trading.model import (
    AccountSnapshot,
    BrokerOrder,
    MarketQuote,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradingMode,
)
from trading.reconciliation import ReconciliationResult
from trading.risk import (
    RiskContext,
    RiskLimits,
    RiskManager,
    RiskReason,
)


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


class TradingRiskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = RiskManager(RiskLimits(
            max_order_value=Decimal("1000000"),
            max_position_value=Decimal("2000000"),
            max_gross_exposure=Decimal("5000000"),
            max_daily_loss=Decimal("100000"),
            max_open_orders=2,
            allowed_symbols=frozenset({"005930"}),
        ))
        self.account = AccountSnapshot(
            "account-ref", NOW, Decimal("3000000"), Decimal("3000000"),
            (Position("005930", 10, Decimal("70000"), Decimal("70000")),),
        )
        self.quote = MarketQuote(
            "005930", NOW, Decimal("70000"), Decimal("69900"),
            Decimal("70100"),
        )

    def intent(self, *, side=OrderSide.BUY, quantity=1, intent_id="intent-1"):
        return OrderIntent(
            intent_id, "candidate", "005930", side, quantity,
            OrderType.LIMIT, NOW, Decimal("70000"),
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

    def test_approves_bounded_reconciled_paper_request(self) -> None:
        decision = self.manager.evaluate(self.intent(), self.context())

        self.assertTrue(decision.approved)
        self.assertEqual((RiskReason.APPROVED,), decision.reasons)
        self.assertEqual("intent-1", decision.request.intent_id)

    def test_live_mode_is_locked_by_default(self) -> None:
        decision = self.manager.evaluate(
            self.intent(), self.context(mode=TradingMode.LIVE)
        )

        self.assertFalse(decision.approved)
        self.assertIn(RiskReason.LIVE_TRADING_DISABLED, decision.reasons)

    def test_reconciliation_and_kill_switch_are_fail_closed(self) -> None:
        decision = self.manager.evaluate(self.intent(), self.context(
            reconciliation=ReconciliationResult(False, ()),
            kill_switch_active=True,
        ))

        self.assertFalse(decision.approved)
        self.assertIn(RiskReason.ACCOUNT_NOT_RECONCILED, decision.reasons)
        self.assertIn(RiskReason.KILL_SWITCH_ACTIVE, decision.reasons)

    def test_stale_quote_and_account_are_rejected(self) -> None:
        stale_account = AccountSnapshot(
            "account-ref", NOW - timedelta(minutes=1),
            Decimal("3000000"), Decimal("3000000"), self.account.positions,
        )
        stale_quote = MarketQuote(
            "005930", NOW - timedelta(seconds=6), Decimal("70000")
        )
        decision = self.manager.evaluate(self.intent(), self.context(
            account=stale_account, quote=stale_quote,
        ))

        self.assertIn(RiskReason.ACCOUNT_SNAPSHOT_STALE, decision.reasons)
        self.assertIn(RiskReason.QUOTE_MISSING_OR_STALE, decision.reasons)

    def test_stale_or_future_intent_is_rejected(self) -> None:
        stale = OrderIntent(
            "stale", "candidate", "005930", OrderSide.BUY, 1,
            OrderType.LIMIT, NOW - timedelta(seconds=31), Decimal("70000"),
        )
        future = OrderIntent(
            "future", "candidate", "005930", OrderSide.BUY, 1,
            OrderType.LIMIT, NOW + timedelta(seconds=1), Decimal("70000"),
        )

        self.assertIn(
            RiskReason.ORDER_INTENT_STALE,
            self.manager.evaluate(stale, self.context()).reasons,
        )
        self.assertIn(
            RiskReason.ORDER_INTENT_STALE,
            self.manager.evaluate(future, self.context()).reasons,
        )

    def test_duplicate_and_daily_loss_are_rejected(self) -> None:
        decision = self.manager.evaluate(self.intent(), self.context(
            seen_intent_ids=frozenset({"intent-1"}),
            realized_pnl_today=Decimal("-100000"),
        ))

        self.assertIn(RiskReason.DUPLICATE_INTENT, decision.reasons)
        self.assertIn(RiskReason.DAILY_LOSS_LIMIT, decision.reasons)

    def test_order_and_exposure_limits_are_rejected(self) -> None:
        decision = self.manager.evaluate(
            self.intent(quantity=20), self.context()
        )

        self.assertIn(RiskReason.ORDER_VALUE_LIMIT, decision.reasons)
        self.assertIn(RiskReason.POSITION_VALUE_LIMIT, decision.reasons)

    def test_cannot_sell_more_than_available_after_pending_sell(self) -> None:
        pending = BrokerOrder(
            "order-1", "old-intent", "005930", OrderSide.SELL,
            8, 0, OrderStatus.ACCEPTED, NOW, Decimal("70000"),
        )
        decision = self.manager.evaluate(
            self.intent(side=OrderSide.SELL, quantity=3),
            self.context(open_orders=(pending,)),
        )

        self.assertIn(RiskReason.INSUFFICIENT_POSITION, decision.reasons)

    def test_external_cash_reservation_is_included(self) -> None:
        decision = self.manager.evaluate(
            self.intent(),
            self.context(reserved_buying_power=Decimal("2950000")),
        )

        self.assertIn(RiskReason.INSUFFICIENT_BUYING_POWER, decision.reasons)


if __name__ == "__main__":
    unittest.main()
