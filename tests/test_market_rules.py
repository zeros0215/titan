import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trading.market_rules import (
    MarketRuleReason,
    MarketRulesSnapshot,
    validate_market_order,
)
from trading.model import OrderIntent, OrderSide, OrderType


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


class MarketRulesTest(unittest.TestCase):
    def rules(self, **changes):
        values = {
            "symbol": "005930",
            "venue": "KRX",
            "observed_at": NOW,
            "regular_session_open": True,
            "reference_price": Decimal("70000"),
            "lower_limit_price": Decimal("49000"),
            "upper_limit_price": Decimal("91000"),
            "tick_size": Decimal("100"),
        }
        values.update(changes)
        return MarketRulesSnapshot(**values)

    def intent(self, order_type=OrderType.LIMIT, price=Decimal("70100")):
        return OrderIntent(
            "intent-1", "candidate", "005930", OrderSide.BUY, 1,
            order_type, NOW, price if order_type is OrderType.LIMIT else None,
        )

    def evaluate(self, intent=None, rules=None):
        return validate_market_order(
            intent or self.intent(), rules or self.rules(), now=NOW,
            maximum_age_seconds=5,
        )

    def test_accepts_regular_krx_limit_order_on_tick(self) -> None:
        self.assertTrue(self.evaluate().approved)

    def test_market_order_does_not_require_limit_price(self) -> None:
        self.assertTrue(self.evaluate(
            self.intent(OrderType.MARKET, None)
        ).approved)

    def test_rejects_closed_session(self) -> None:
        decision = self.evaluate(rules=self.rules(regular_session_open=False))
        self.assertIn(MarketRuleReason.SESSION_NOT_REGULAR, decision.reasons)

    def test_rejects_stale_or_future_rules(self) -> None:
        stale = self.evaluate(rules=self.rules(
            observed_at=NOW - timedelta(seconds=6)
        ))
        future = self.evaluate(rules=self.rules(
            observed_at=NOW + timedelta(seconds=1)
        ))
        self.assertIn(MarketRuleReason.RULES_STALE, stale.reasons)
        self.assertIn(MarketRuleReason.RULES_STALE, future.reasons)

    def test_rejects_limit_price_off_tick_or_outside_daily_range(self) -> None:
        off_tick = self.evaluate(self.intent(price=Decimal("70050")))
        outside = self.evaluate(self.intent(price=Decimal("92000")))
        self.assertIn(MarketRuleReason.LIMIT_PRICE_OFF_TICK, off_tick.reasons)
        self.assertIn(
            MarketRuleReason.LIMIT_PRICE_OUTSIDE_DAILY_RANGE, outside.reasons
        )

    def test_rejects_invalid_broker_boundaries(self) -> None:
        with self.assertRaisesRegex(ValueError, "30 percent"):
            self.rules(upper_limit_price=Decimal("92000"))
        with self.assertRaisesRegex(ValueError, "six-digit"):
            self.rules(symbol="A05930")


if __name__ == "__main__":
    unittest.main()
