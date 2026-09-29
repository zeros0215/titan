import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from broker.kiwoom import KiwoomPaperOrderObservation
from trading.model import BrokerOrderRequest, OrderSide, OrderType
from trading.order_lookup import OrderLookupStatus, resolve_uncertain_submission


SEOUL = ZoneInfo("Asia/Seoul")
STARTED = datetime(2026, 9, 29, 9, 0, 10, tzinfo=SEOUL)


def observation(order_id, *, seconds=2, symbol="005930", quantity=1):
    return KiwoomPaperOrderObservation(
        order_id,
        symbol,
        OrderSide.BUY,
        quantity,
        0,
        quantity,
        Decimal("0"),
        STARTED + timedelta(seconds=seconds),
        "KRX",
    )


class OrderLookupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.request = BrokerOrderRequest(
            "intent-1", "005930", OrderSide.BUY, 1,
            OrderType.MARKET, None,
        )

    def resolve(self, observations, known=frozenset()):
        return resolve_uncertain_submission(
            self.request,
            submission_started_at=STARTED,
            known_order_ids_before_submit=known,
            observations=tuple(observations),
        )

    def test_resolves_one_unique_new_order(self) -> None:
        result = self.resolve([observation("24")])
        self.assertEqual(OrderLookupStatus.FOUND, result.status)
        self.assertEqual("24", result.order.broker_order_id)

    def test_excludes_orders_known_before_submission(self) -> None:
        result = self.resolve(
            [observation("23"), observation("24")],
            known=frozenset({"23"}),
        )
        self.assertEqual(OrderLookupStatus.FOUND, result.status)
        self.assertEqual("24", result.order.broker_order_id)

    def test_zero_matches_stays_unresolved(self) -> None:
        result = self.resolve([observation("24", symbol="000660")])
        self.assertEqual(OrderLookupStatus.NOT_FOUND, result.status)
        self.assertIsNone(result.order)

    def test_multiple_matches_are_ambiguous_and_never_guessed(self) -> None:
        result = self.resolve([observation("24"), observation("25")])
        self.assertEqual(OrderLookupStatus.AMBIGUOUS, result.status)
        self.assertIsNone(result.order)
        self.assertEqual(("24", "25"), result.matching_order_ids)

    def test_rejects_orders_outside_time_window_or_wrong_quantity(self) -> None:
        too_late = observation("24", seconds=121)
        wrong_quantity = observation("25", quantity=2)
        result = self.resolve([too_late, wrong_quantity])
        self.assertEqual(OrderLookupStatus.NOT_FOUND, result.status)

    def test_timezone_conversion_is_used_for_comparison(self) -> None:
        utc_observation = observation("24")
        utc_observation = KiwoomPaperOrderObservation(
            utc_observation.broker_order_id,
            utc_observation.symbol,
            utc_observation.side,
            utc_observation.requested_quantity,
            utc_observation.filled_quantity,
            utc_observation.remaining_quantity,
            utc_observation.order_price,
            utc_observation.ordered_at.astimezone(timezone.utc),
            utc_observation.venue,
        )
        result = self.resolve([utc_observation])
        self.assertEqual(OrderLookupStatus.FOUND, result.status)


if __name__ == "__main__":
    unittest.main()
