"""
Market Series
"""

from dataclasses import dataclass

from market.market_candle import MarketCandle


@dataclass(slots=True)
class MarketSeries:

    name: str

    candles: list[MarketCandle]

    @property
    def latest(self):

        return self.candles[-1]

    @property
    def closes(self):

        return [

            c.close

            for c in self.candles

        ]

    @property
    def volumes(self):

        return [

            c.volume

            for c in self.candles

        ]