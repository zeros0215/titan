"""
Breakout Indicator
"""

from dataclasses import dataclass

from domain.candle_series import CandleSeries



@dataclass(slots=True)
class BreakoutResult:

    price_position: float



def calculate(
    series: CandleSeries
) -> BreakoutResult:


    if len(series.highs) < 60:
        raise ValueError(
            "Need at least 60 candles"
        )


    high60 = max(
        series.highs[-60:]
    )


    position = (
        series.closes[-1]
        /
        high60
    )


    return BreakoutResult(

        price_position=position

    )