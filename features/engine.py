"""
Feature Engine
"""

from features.feature import Feature

from features.moving_average import MovingAverage
from features.volume import VolumeFeature
from features.momentum import MomentumFeature
from features.breakout import BreakoutFeature
from features.volatility import VolatilityFeature


class FeatureEngine:

    def calculate(self, series):

        closes = series.closes
        volumes = series.volumes
        trading_values = series.trading_values

        return Feature(

            #
            # Price
            #
            close=closes[-1],

            #
            # Moving Average
            #
            ma5=MovingAverage.calculate(closes, 5),
            ma20=MovingAverage.calculate(closes, 20),
            ma60=MovingAverage.calculate(closes, 60),
            ma120=MovingAverage.calculate(closes, 120),
            ma240=MovingAverage.calculate(closes, 240),

            #
            # Volume
            #
            volume=volumes[-1],
            volume_ma20=VolumeFeature.average(volumes),
            volume_ratio=VolumeFeature.ratio(volumes),

            #
            # Trading Value
            #
            trading_value=trading_values[-1],
            trading_value_ma20=(
                sum(trading_values[-20:]) /
                min(len(trading_values), 20)
            ),

            #
            # Momentum
            #
            momentum5=MomentumFeature.rate(closes, 5),
            momentum20=MomentumFeature.rate(closes, 20),

            #
            # ATR
            #
            atr14=VolatilityFeature.atr(series),

            #
            # Breakout
            #
            highest20=BreakoutFeature.highest(closes, 20),
            lowest20=BreakoutFeature.lowest(closes, 20),

            #
            # 52 Weeks
            #
            high52=max(closes),
            low52=min(closes)
        )