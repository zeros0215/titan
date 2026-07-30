from domain.candle_series import CandleSeries
from indicators.calculators.base_calculator import BaseCalculator
from indicators.momentum_result import MomentumResult


class MomentumCalculator(BaseCalculator):

    def calculate(self, series: CandleSeries) -> MomentumResult:

        closes = series.closes

        if len(closes) < 21:
            raise ValueError("Need at least 21 candles.")

        latest = closes[-1]

        close_5 = closes[-6]
        close_20 = closes[-21]

        momentum_5 = ((latest - close_5) / close_5) * 100
        momentum_20 = ((latest - close_20) / close_20) * 100

        acceleration = momentum_5 - momentum_20

        return MomentumResult(
            momentum_5=momentum_5,
            momentum_20=momentum_20,
            acceleration=acceleration
        )