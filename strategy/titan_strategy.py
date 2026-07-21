"""
TITAN Strategy
"""

from strategy.signal import Signal

from strategy.strategy_result import StrategyResult


class TitanStrategy:

    BUY_SCORE = 80

    WATCH_SCORE = 60

    SELL_SCORE = 30

    def evaluate(self, factor):

        score = factor.total

        #
        # BUY
        #
        if score >= self.BUY_SCORE:

            return StrategyResult(

                signal=Signal.BUY,

                score=score,

                reason="High Score"

            )

        #
        # WATCH
        #
        if score >= self.WATCH_SCORE:

            return StrategyResult(

                signal=Signal.HOLD,

                score=score,

                reason="Watch"

            )

        #
        # SELL
        #
        if score <= self.SELL_SCORE:

            return StrategyResult(

                signal=Signal.SELL,

                score=score,

                reason="Weak"

            )

        return StrategyResult(

            signal=Signal.HOLD,

            score=score,

            reason="Neutral"

        )