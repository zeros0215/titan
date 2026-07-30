from datetime import datetime
import unittest

from broker.mock.market import MockMarketProvider
from broker.mock.scenario import MarketScenario
from domain.enums import MarketType
from domain.stock import Stock


class MockMarketProviderTest(unittest.TestCase):
    def test_returns_identical_candles_for_the_same_fixed_scenario(self) -> None:
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        provider = MockMarketProvider(
            scenario=MarketScenario.BULL,
            reference_date=datetime(2026, 7, 27),
        )

        first = provider.get_daily_price(stock)
        second = provider.get_daily_price(stock)

        self.assertEqual(first.candles, second.candles)
        self.assertEqual(len(first), 100)

    def test_scenarios_produce_different_price_paths(self) -> None:
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        reference = datetime(2026, 7, 27)
        bull = MockMarketProvider(MarketScenario.BULL, reference).get_daily_price(stock)
        bear = MockMarketProvider(MarketScenario.BEAR, reference).get_daily_price(stock)

        self.assertNotEqual(bull.latest.close, bear.latest.close)

    def test_returns_only_the_requested_date_range(self) -> None:
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        provider = MockMarketProvider(MarketScenario.BULL)
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 10)

        series = provider.get_daily_prices(stock, start, end)

        self.assertEqual(series.candles[0].date, start)
        self.assertEqual(series.candles[-1].date, end)
        self.assertEqual(len(series), 10)


if __name__ == "__main__":
    unittest.main()
