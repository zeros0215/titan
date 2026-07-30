import unittest
from datetime import datetime

from broker.mock.market import MockMarketProvider
from broker.mock.scenario import MarketScenario
from data.quality import CandleSeriesValidator
from domain.enums import MarketType
from domain.stock import Stock
from scanner.scanner import Scanner


class _PartiallyFailingProvider(MockMarketProvider):
    def get_daily_prices(self, stock, start_date, end_date):
        if stock.code == "000002":
            raise RuntimeError("fixture failure")
        return super().get_daily_prices(stock, start_date, end_date)


class _Analyzer:
    def analyze(self, stock, series, context):
        return stock


class ScannerFailureTest(unittest.TestCase):
    def test_one_fetch_failure_does_not_abort_other_stocks(self):
        scanner = Scanner(
            _PartiallyFailingProvider(MarketScenario.BULL),
            _Analyzer(),
            quality_validator=CandleSeriesValidator(minimum_candles=1),
        )
        stocks = [
            Stock("000001", "Success", MarketType.KOSPI),
            Stock("000002", "Failure", MarketType.KOSPI),
        ]

        result = scanner.scan_with_market_data(
            stocks,
            as_of=datetime(2026, 7, 28),
        )

        self.assertEqual(1, len(result.analyses))
        self.assertIn("000002", result.fetch_failures)
        self.assertEqual(2, result.quality_summary.total_count)
        self.assertEqual(1, result.quality_summary.excluded_count)
        self.assertEqual(
            1,
            result.quality_summary.issues_by_code["FETCH_ERROR"],
        )


if __name__ == "__main__":
    unittest.main()
