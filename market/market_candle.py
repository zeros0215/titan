"""
Market Candle
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class MarketCandle:

    date: datetime

    open: float

    high: float

    low: float

    close: float

    volume: float

    advance_count: int

    decline_count: int