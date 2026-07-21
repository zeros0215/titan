"""
OHLCV Candle Domain
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Candle:

    date: datetime

    open: float

    high: float

    low: float

    close: float

    volume: int

    @property
    def trading_value(self) -> float:
        """
        거래대금
        """

        return self.close * self.volume