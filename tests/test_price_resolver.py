from datetime import datetime, timedelta
import unittest

from analysis.analysis_result import AnalysisResult
from backtest.model.selection import Selection
from backtest.price_resolver import CandlePriceResolver
from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.enums import MarketType
from domain.stock import Stock
from scoring.score_result import ScoreResult


class CandlePriceResolverTest(unittest.TestCase):
    def test_uses_next_session_open_for_entry(self) -> None:
        start = datetime(2026, 1, 1)
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        series = CandleSeries(stock, [
            self._candle(start, 100.0),
            self._candle(start + timedelta(days=1), 110.0),
            self._candle(start + timedelta(days=2), 120.0),
        ])
        selection = Selection(
            AnalysisResult("000001", "Alpha", None, None, ScoreResult()),
            start + timedelta(days=1, hours=12),
            1,
        )

        prices = CandlePriceResolver().resolve(
            [selection],
            {"000001": series},
            start + timedelta(days=2, hours=12),
        )

        self.assertEqual(prices.selection_prices["000001"], 120.0)
        self.assertEqual(prices.evaluation_prices["000001"], 120.0)

    def test_uses_first_available_session_after_signal(self) -> None:
        start = datetime(2026, 1, 1)
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        series = CandleSeries(stock, [self._candle(start, 100.0)])
        selection = Selection(
            AnalysisResult("000001", "Alpha", None, None, ScoreResult()),
            start - timedelta(days=1),
            1,
        )

        prices = CandlePriceResolver().resolve([selection], {"000001": series}, start)

        self.assertEqual(prices.selection_prices["000001"], 100.0)

    def test_rejects_clock_time_without_intraday_candles(self) -> None:
        start = datetime(2026, 1, 2, 10, 0)
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        series = CandleSeries(stock, [
            self._candle(datetime(2026, 1, 2, 9, 0), 100.0),
            self._candle(datetime(2026, 1, 2, 15, 0), 110.0),
            self._candle(datetime(2026, 1, 5, 15, 0), 120.0),
        ])
        selection = Selection(
            AnalysisResult("000001", "Alpha", None, None, ScoreResult()),
            datetime(2026, 1, 2, 15, 0),
            1,
        )

        with self.assertRaisesRegex(ValueError, "intraday candles"):
            CandlePriceResolver().resolve(
                [selection],
                {"000001": series},
                datetime(2026, 1, 5, 15, 0),
                trade_time="10:00",
                sell_time="14:00",
            )

    def test_returns_no_entry_when_next_session_is_unavailable(self) -> None:
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        series = CandleSeries(stock, [
            self._candle(datetime(2026, 1, 2), 100.0),
            self._candle(datetime(2026, 1, 5), 120.0),
        ])
        selection = Selection(
            AnalysisResult("000001", "Alpha", None, None, ScoreResult()),
            datetime(2026, 1, 5),
            1,
        )

        prices = CandlePriceResolver().resolve(
            [selection],
            {"000001": series},
            datetime(2026, 1, 5),
        )

        self.assertNotIn("000001", prices.selection_prices)
        self.assertEqual(prices.evaluation_prices["000001"], 120.0)

    @staticmethod
    def _candle(date: datetime, close: float) -> Candle:
        return Candle(date, close, close, close, close, 1_000)


if __name__ == "__main__":
    unittest.main()
