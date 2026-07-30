from .market_trend import MarketTrend


class MarketStrengthCalculator:

    def calculate_strength(
        self,
        advancing: int,
        declining: int,
    ) -> float:

        total = advancing + declining

        if total == 0:
            return 0.0

        return advancing / total

    def determine_trend(
        self,
        market_return: float
    ) -> MarketTrend:

        if market_return >= 1.5:
            return MarketTrend.BULL

        if market_return <= -1.5:
            return MarketTrend.BEAR

        return MarketTrend.SIDEWAYS

    def calculate_score(
        self,
        strength: float
    ) -> int:

        if strength >= 0.8:
            return 20

        if strength >= 0.7:
            return 15

        if strength >= 0.6:
            return 10

        if strength >= 0.5:
            return 5

        return 0