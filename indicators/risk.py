"""
Risk Indicator
"""

from dataclasses import dataclass

from domain.candle_series import CandleSeries



@dataclass(slots=True)
class RiskResult:

    change_20d: float



def calculate(
    series: CandleSeries
) -> RiskResult:


    closes = series.closes


    change = (
        closes[-1]
        /
        closes[-20]
        - 1
    )


    return RiskResult(

        change_20d=change

    )