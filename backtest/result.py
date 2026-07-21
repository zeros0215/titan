"""
TITAN Backtest Result
"""

from dataclasses import dataclass

from backtest.trade import Trade
from backtest.equity import EquityCurve
from backtest.performance import PerformanceAnalyzer



@dataclass(slots=True)
class BacktestResult:


    trades: list[Trade]

    #
    # Candle 기반 Equity 데이터
    #
    equity_data: list[dict] | None = None



    @property
    def total_trades(self) -> int:

        return len(self.trades)



    @property
    def winning_trades(self):

        return [

            t for t in self.trades

            if t.return_rate > 0

        ]



    @property
    def losing_trades(self):

        return [

            t for t in self.trades

            if t.return_rate <= 0

        ]



    @property
    def win_rate(self) -> float:


        if not self.trades:

            return 0.0


        return (

            len(self.winning_trades)

            /

            len(self.trades)

            *

            100

        )



    @property
    def total_return(self) -> float:


        if not self.trades:

            return 0.0


        return sum(

            trade.return_rate

            for trade in self.trades

        )



    @property
    def average_return(self):


        if not self.trades:

            return 0.0


        return (

            self.total_return

            /

            len(self.trades)

        )



    @property
    def profit_factor(self):


        profit = sum(

            t.return_rate

            for t in self.winning_trades

        )


        loss = abs(

            sum(

                t.return_rate

                for t in self.losing_trades

            )

        )


        if loss == 0:

            if profit > 0:

                return float("inf")


            return 0.0


        return profit / loss



    @property
    def avg_holding_days(self):


        if not self.trades:

            return 0



        total = 0

        count = 0



        for trade in self.trades:


            if trade.buy_date and trade.sell_date:


                days = (

                    trade.sell_date

                    -

                    trade.buy_date

                ).days


                total += days

                count += 1



        if count == 0:

            return 0



        return total / count




    @property
    def equity_curve(self):


        if not self.equity_data:

            return []


        return EquityCurve().calculate(

            self.equity_data

        )



    @property
    def max_drawdown(self):


        return PerformanceAnalyzer().max_drawdown(

            self.equity_curve

        )



    @property
    def final_equity(self):


        return PerformanceAnalyzer().final_equity(

            self.equity_curve

        )