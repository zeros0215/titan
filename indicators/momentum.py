"""
Momentum Indicator
"""

from dataclasses import dataclass

from domain.candle_series import CandleSeries



@dataclass(slots=True)
class MomentumResult:

    change_5d: float

    change_20d: float



def calculate(
    series: CandleSeries
) -> MomentumResult:


    closes = series.closes


    if len(closes) < 21:
        raise ValueError(
            "Need at least 21 candles"
        )


    latest = closes[-1]


    change_5d = (
        latest / closes[-6]
        - 1
    )


    change_20d = (
        latest / closes[-21]
        - 1
    )


    return MomentumResult(

        change_5d=change_5d,

        change_20d=change_20d

    )