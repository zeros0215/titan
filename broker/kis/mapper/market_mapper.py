"""
Market Mapper
"""

from datetime import datetime

from broker.kis.dto.market_response import DailyPriceResponse

from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.stock import Stock


class MarketMapper:

    @staticmethod
    def to_candle_series(
        stock: Stock,
        dto: DailyPriceResponse
    ) -> CandleSeries:

        candles = [
            Candle(
                date=datetime.strptime(
                    item.date,
                    "%Y%m%d"
                ),
                open=float(item.open),
                high=float(item.high),
                low=float(item.low),
                close=float(item.close),
                volume=int(item.volume)
            )
            for item in reversed(dto.output2)
        ]

        return CandleSeries(
            stock=stock,
            candles=candles
        )