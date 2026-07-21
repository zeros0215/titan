from domain.candle_series import CandleSeries

from indicators.bundle import IndicatorBundle

from indicators import (
    moving_average,
    momentum,
    volume,
    breakout,
    risk,
    rsi
)


class IndicatorCalculator:

    def calculate(
        self,
        series: CandleSeries
    ) -> IndicatorBundle:

        return IndicatorBundle(

            moving_average=
            moving_average.calculate(series),


            momentum=
            momentum.calculate(series),


            volume=
            volume.calculate(series),


            breakout=
            breakout.calculate(series),


            risk=
            risk.calculate(series),


            rsi=
            rsi.calculate(series)

        )