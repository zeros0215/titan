"""
Backtest Service
"""

from backtest.engine import BacktestEngine


class BacktestService:

    def __init__(self):

        self.engine = BacktestEngine()

    def run(

        self,

        history,

        strategy

    ):

        return self.engine.run(

            history,

            strategy

        )