"""
Feature Builder
"""

from feature.bundle import FeatureBundle
from indicators.bundle import IndicatorBundle


class FeatureBuilder:

    def build(
        self,
        indicators: IndicatorBundle
    ) -> FeatureBundle:

        return FeatureBundle(

            trend_strength=self._trend(indicators),

            volume_strength=self._volume(indicators),

            momentum_strength=self._momentum(indicators),

            breakout_strength=self._breakout(indicators),

            risk_strength=self._risk(indicators)

        )
    

    def _trend(self, indicators):

        score = 0

        ma = indicators.moving_average

        if ma.price_above_ma20:
            score += 0.4

        if ma.ma5_above_ma20:
            score += 0.3

        if ma.ma20_above_ma60:
            score += 0.3

        return score    
    
    def _volume(self, indicators):

        ratio = indicators.volume.volume_ratio

        return min(
            ratio / 2,
            1
        )

    def _momentum(self, indicators):

        value = indicators.momentum.change_20d

        if value <= 0:
            return 0

        return min(
            value / 0.2,
            1
        )

    def _breakout(self, indicators):

        return indicators.breakout.price_position

    def _risk(self, indicators):

        change = indicators.risk.change_20d

        if change >= 0:
            return 0

        return min(
            abs(change) / 0.2,
            1
        )

