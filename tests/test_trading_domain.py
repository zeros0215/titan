import unittest
from datetime import datetime, timezone
from decimal import Decimal

from trading.model import (
    AccountSnapshot,
    Fill,
    OrderIntent,
    OrderSide,
    OrderType,
    Position,
)


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


class TradingDomainTest(unittest.TestCase):
    def test_limit_intent_requires_a_positive_price(self) -> None:
        with self.assertRaises(ValueError):
            OrderIntent(
                "intent-1", "strategy", "005930", OrderSide.BUY, 1,
                OrderType.LIMIT, NOW,
            )

    def test_intent_rejects_naive_timestamp(self) -> None:
        with self.assertRaises(ValueError):
            OrderIntent(
                "intent-1", "strategy", "005930", OrderSide.BUY, 1,
                OrderType.MARKET, datetime(2026, 9, 29, 9, 0),
            )

    def test_account_rejects_duplicate_positions(self) -> None:
        position = Position("005930", 1, Decimal("70000"), Decimal("71000"))
        with self.assertRaises(ValueError):
            AccountSnapshot(
                "account-ref", NOW, Decimal("100000"), Decimal("100000"),
                (position, position),
            )

    def test_fill_rejects_quantity_or_price_without_value(self) -> None:
        with self.assertRaises(ValueError):
            Fill(
                "order-1", "fill-1", "005930", OrderSide.BUY,
                0, Decimal("70000"), Decimal("0"), NOW,
            )


if __name__ == "__main__":
    unittest.main()
