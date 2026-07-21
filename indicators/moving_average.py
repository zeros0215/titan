"""
Moving Average Indicator
"""

from dataclasses import dataclass

from domain.candle_series import CandleSeries


@dataclass(slots=True)
class MovingAverageResult:

    ma5: float

    ma20: float

    ma60: float

    price_above_ma20: bool

    ma5_above_ma20: bool

    ma20_above_ma60: bool



def calculate(
    series: CandleSeries
) -> MovingAverageResult:


    closes = series.closes


    if len(closes) < 60:
        raise ValueError(
            "Need at least 60 candles"
        )


    ma5 = (
        sum(closes[-5:]) / 5
    )


    ma20 = (
        sum(closes[-20:]) / 20
    )


    ma60 = (
        sum(closes[-60:]) / 60
    )


    price = closes[-1]


    return MovingAverageResult(

        ma5=ma5,

        ma20=ma20,

        ma60=ma60,

        price_above_ma20=(
            price > ma20
        ),

        ma5_above_ma20=(
            ma5 > ma20
        ),

        ma20_above_ma60=(
            ma20 > ma60
        )

    )