"""
Factor Engine
"""

from factors.factor_score import FactorScore

from factors.trend import TrendFactor
from factors.momentum import MomentumFactor
from factors.volume import VolumeFactor
from factors.breakout import BreakoutFactor
from factors.risk import RiskFactor


class FactorEngine:

    def __init__(self):

        self.trend = TrendFactor()

        self.momentum = MomentumFactor()

        self.volume = VolumeFactor()

        self.breakout = BreakoutFactor()

        self.risk = RiskFactor()

    def calculate(self, feature) -> FactorScore:

        trend_score = self.trend.calculate(feature)

        momentum_score = self.momentum.calculate(feature)

        volume_score = self.volume.calculate(feature)

        breakout_score = self.breakout.calculate(feature)

        risk_score = self.risk.calculate(feature)

        total = int(

            trend_score * 0.30 +

            momentum_score * 0.20 +

            volume_score * 0.20 +

            breakout_score * 0.20 +

            risk_score * 0.10

        )

        return FactorScore(

            trend=trend_score,

            momentum=momentum_score,

            volume=volume_score,

            breakout=breakout_score,

            risk=risk_score,

            total=total

        )