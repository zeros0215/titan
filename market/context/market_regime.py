from enum import Enum

from market.context.market_context import MarketContext
from market.context.market_trend import MarketTrend


class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    MIXED = "MIXED"


class MarketRegimeClassifier:
    """Classify only from Context facts currently collected by TITAN V1."""

    @staticmethod
    def classify(context: MarketContext) -> MarketRegime:
        trends = {context.kospi_trend, context.kosdaq_trend}
        if trends == {MarketTrend.BULL}:
            return MarketRegime.BULL
        if trends == {MarketTrend.BEAR}:
            return MarketRegime.BEAR
        if trends == {MarketTrend.SIDEWAYS}:
            return MarketRegime.SIDEWAYS
        if (
            MarketTrend.BEAR not in trends
            and context.market_strength >= 0.6
        ):
            return MarketRegime.BULL
        if (
            MarketTrend.BULL not in trends
            and context.market_strength < 0.4
        ):
            return MarketRegime.BEAR
        return MarketRegime.MIXED
