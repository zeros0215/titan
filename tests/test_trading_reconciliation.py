import unittest
from datetime import datetime, timezone
from decimal import Decimal

from trading.model import AccountSnapshot, Position
from trading.reconciliation import (
    DifferenceType,
    InternalPortfolioSnapshot,
    reconcile_account,
)


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


def position(quantity=10, average="70000"):
    return Position(
        "005930", quantity, Decimal(average), Decimal("71000")
    )


class TradingReconciliationTest(unittest.TestCase):
    def test_matching_account_is_ready(self) -> None:
        local = InternalPortfolioSnapshot(
            Decimal("1000000"), (position(),), frozenset({"order-1"})
        )
        broker = AccountSnapshot(
            "account-ref", NOW, Decimal("1000000"), Decimal("500000"),
            (position(),),
        )

        result = reconcile_account(
            local, broker, frozenset({"order-1"})
        )

        self.assertTrue(result.ready)
        self.assertEqual((), result.differences)

    def test_any_position_or_unknown_order_difference_blocks(self) -> None:
        local = InternalPortfolioSnapshot(
            Decimal("1000000"), (position(quantity=10),), frozenset()
        )
        broker = AccountSnapshot(
            "account-ref", NOW, Decimal("1000000"), Decimal("500000"),
            (position(quantity=9),),
        )

        result = reconcile_account(
            local, broker, frozenset({"unknown-order"})
        )

        self.assertFalse(result.ready)
        self.assertEqual(
            {DifferenceType.POSITION_QUANTITY, DifferenceType.UNKNOWN_OPEN_ORDER},
            {item.kind for item in result.differences},
        )


if __name__ == "__main__":
    unittest.main()
