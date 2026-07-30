from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.enums import MarketType
from domain.stock import Stock
from repository.candle_repository import CandleRepository


class CandleRepositoryTest(unittest.TestCase):
    def test_persists_and_merges_cached_and_fetched_candles(self) -> None:
        start = datetime(2026, 1, 1)
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        cached = CandleSeries(stock, [self._candle(start, 100.0)])
        fetched = CandleSeries(stock, [
            self._candle(start + timedelta(days=1), 110.0),
        ])
        with TemporaryDirectory() as directory:
            repository = CandleRepository(Path(directory))
            repository.save(cached)
            merged = CandleRepository.merge(repository.load("000001"), fetched)
            repository.save(merged)
            loaded = repository.load("000001")

        self.assertEqual([candle.close for candle in loaded.candles], [100.0, 110.0])

    @staticmethod
    def _candle(date: datetime, close: float) -> Candle:
        return Candle(date, close, close, close, close, 1_000)


if __name__ == "__main__":
    unittest.main()
