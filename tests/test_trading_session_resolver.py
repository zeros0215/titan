from datetime import datetime, timedelta
import unittest

from backtest.trading_session_resolver import TradingSessionResolver
from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.enums import MarketType
from domain.stock import Stock


class TradingSessionResolverTest(unittest.TestCase):
    def test_resolves_observed_sessions_not_calendar_days(self) -> None:
        selected_at = datetime(2026, 1, 2)
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        session_dates = [
            datetime(2026, 1, 5),
            datetime(2026, 1, 6),
            datetime(2026, 1, 7),
            datetime(2026, 1, 8),
            datetime(2026, 1, 9),
            datetime(2026, 1, 12),
        ]
        series = CandleSeries(stock, [
            Candle(date, 100, 100, 100, 100, 1_000)
            for date in session_dates
        ])

        resolved = TradingSessionResolver.resolve(
            {stock.code: series},
            selected_at,
            [5, 6],
            selected_at + timedelta(days=20),
        )

        self.assertEqual(resolved[5], datetime(2026, 1, 9))
        self.assertEqual(resolved[6], datetime(2026, 1, 12))

    def test_rejects_insufficient_sessions(self) -> None:
        with self.assertRaisesRegex(ValueError, "insufficient"):
            TradingSessionResolver.resolve(
                {},
                datetime(2026, 1, 1),
                [5],
                datetime(2026, 2, 1),
            )


if __name__ == "__main__":
    unittest.main()
