"""
Market Factor Engine
"""

from market.market_factor import MarketFactor

from market.indicators.trend import TrendIndicator
from market.indicators.volume import VolumeIndicator
from market.indicators.volatility import VolatilityIndicator
from market.indicators.breadth import BreadthIndicator


class MarketFactorEngine:

    def __init__(self):

        self.trend = TrendIndicator()

        self.volume = VolumeIndicator()

        self.volatility = VolatilityIndicator()

        self.breadth = BreadthIndicator()

    def calculate(self, feature):

        trend = self.trend.calculate(feature)

        volume = self.volume.calculate(feature)

        volatility = self.volatility.calculate(feature)

        breadth = self.breadth.calculate(feature)

        confidence = int(

            trend * 0.35 +

            volume * 0.20 +

            breadth * 0.25 +

            volatility * 0.20

        )

        return MarketFactor(

            trend=trend,

            volume=volume,

            volatility=volatility,

            breadth=breadth,

            confidence=confidence,

            total=confidence

        )