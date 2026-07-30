"""
Indicator Engine
"""

from domain.candle_series import CandleSeries

from indicators.bundle import IndicatorBundle

from indicators.breakout_calculator import BreakoutCalculator
from indicators.calculators.momentum_calculator import MomentumCalculator
from indicators.calculators.moving_average_calculator import MovingAverageCalculator
from indicators.calculators.risk_calculator import RiskCalculator
from indicators.calculators.volume_calculator import VolumeCalculator


class IndicatorEngine:

    def __init__(self):

        self.moving_average = MovingAverageCalculator()

        self.momentum = MomentumCalculator()

        self.volume = VolumeCalculator()

        self.breakout = BreakoutCalculator()

        self.risk = RiskCalculator()

    def calculate(
        self,
        series: CandleSeries
    ) -> IndicatorBundle:

        return IndicatorBundle(

            moving_average=self.moving_average.calculate(series),

            momentum=self.momentum.calculate(series),

            volume=self.volume.calculate(series),

            breakout=self.breakout.calculate(series),

            risk=self.risk.calculate(series),

        )
