from domain.candle_series import CandleSeries
from indicators.bundle import IndicatorBundle
from indicators.indicator_engine import IndicatorEngine



class IndicatorCalculator:

    def __init__(self) -> None:
        self.engine = IndicatorEngine()


    def calculate(
        self,
        series: CandleSeries
    ) -> IndicatorBundle:


        return self.engine.calculate(series)
