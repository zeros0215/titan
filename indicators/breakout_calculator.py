from domain.candle_series import CandleSeries

from indicators.breakout_result import BreakoutResult
from indicators.calculators.base_calculator import BaseCalculator


class BreakoutCalculator(BaseCalculator):

    def calculate(
        self,
        series: CandleSeries
    ) -> BreakoutResult:

        if len(series.highs) < 60:
            raise ValueError(
                "Need at least 60 candles."
            )

        close = series.closes[-1]

        high20 = max(series.highs[-20:])
        high60 = max(series.highs[-60:])

        return BreakoutResult(

            position20=close / high20,

            position60=close / high60

        )