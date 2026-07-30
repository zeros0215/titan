from domain.candle_series import CandleSeries

from indicators.calculators.base_calculator import BaseCalculator
from indicators.risk_result import RiskResult


class RiskCalculator(BaseCalculator):

    def calculate(
        self,
        series: CandleSeries
    ) -> RiskResult:

        closes = series.closes

        if len(closes) < 20:
            raise ValueError("Need at least 20 candles.")

        change = (
            closes[-1]
            / closes[-20]
            - 1
        )

        return RiskResult(

            change_20d=change

        )