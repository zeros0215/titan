"""Read-only market provider backed by compiled per-stock JSON histories."""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from broker.provider import MarketProvider
from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.stock import Stock


class HistoricalFileMarketProvider(MarketProvider):
    """Serve immutable compiled candles without network access."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        if not directory.exists():
            raise FileNotFoundError(directory)

    @lru_cache(maxsize=None)
    def _candles(self, code: str) -> tuple[Candle, ...]:
        path = self.directory / f"{code}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return tuple(
            Candle(
                date=datetime.fromisoformat(item["date"]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=int(item["volume"]),
            )
            for item in payload.get("candles", [])
        )

    def get_daily_prices(
        self,
        stock: Stock,
        start_date: datetime,
        end_date: datetime,
    ) -> CandleSeries:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        candles = [
            candle
            for candle in self._candles(stock.code)
            if start_date <= candle.date <= end_date
        ]
        return CandleSeries(stock=stock, candles=candles)
