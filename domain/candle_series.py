"""
Candle Series
"""

from dataclasses import dataclass
from datetime import datetime

from domain.candle import Candle
from domain.stock import Stock


@dataclass(slots=True)
class CandleSeries:
    """
    하나의 종목에 대한 OHLCV 집합
    """

    stock: Stock

    candles: list[Candle]

    @property
    def latest(self) -> Candle:
        return self.candles[-1]

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def opens(self) -> list[float]:
        return [c.open for c in self.candles]

    @property
    def highs(self) -> list[float]:
        return [c.high for c in self.candles]

    @property
    def lows(self) -> list[float]:
        return [c.low for c in self.candles]

    @property
    def volumes(self) -> list[int]:
        return [c.volume for c in self.candles]

    @property
    def trading_values(self) -> list[float]:
        return [
            c.close * c.volume
            for c in self.candles
        ]

    def __len__(self) -> int:
        return len(self.candles)

    def until(self, as_of: datetime) -> "CandleSeries":
        """Return the point-in-time view containing no future candles."""
        return CandleSeries(
            stock=self.stock,
            candles=[
                candle
                for candle in self.candles
                if candle.date <= as_of
            ],
        )
