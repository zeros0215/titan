"""
TITAN Backtest Engine
"""


from domain.candle_series import CandleSeries

from backtest.trade import Trade
from backtest.result import BacktestResult

from strategy.exit_rule import ExitRule



class BacktestEngine:


    MIN_HOLD_DAYS = 5

    INITIAL_CAPITAL = 10_000_000



    def __init__(self):

        self.exit_rule = ExitRule()



    def run(
        self,
        series,
        strategy
    ):


        trades = []

        position = None


        #
        # 자산 관리
        #
        capital = self.INITIAL_CAPITAL


        #
        # Candle 기반 Equity
        #
        equity_history = []



        for index, candle in enumerate(series.candles):


            #
            # Indicator 최소 데이터
            #
            if index < 60:

                continue



            history = CandleSeries(

                stock=series.stock,

                candles=series.candles[:index + 1]

            )



            signal = strategy.evaluate(

                history

            )



            #
            # 현재 평가 자산 기록
            #
            if position is not None:


                current_equity = (

                    capital *

                    (

                        candle.close

                        /

                        position.buy_price

                    )

                )


            else:

                current_equity = capital



            equity_history.append(

                {

                    "date": candle.date,

                    "capital": current_equity

                }

            )



            #
            # BUY
            #
            if (

                signal == "BUY"

                and position is None

            ):


                position = Trade(

                    symbol=series.stock.code,

                    buy_date=candle.date,

                    buy_price=candle.close,

                    entry_index=index

                )


                print(

                    "OPEN:",

                    candle.date,

                    candle.close

                )


                continue



            #
            # 보유중이면 EXIT 체크
            #
            if position is not None:



                hold_days = (

                    index

                    -

                    position.entry_index

                )



                if hold_days < self.MIN_HOLD_DAYS:

                    continue



                score = strategy.get_score(

                    history

                )



                exit_flag, reason = (

                    self.exit_rule.should_exit(

                        position,

                        score

                    )

                )



                if exit_flag:


                    position.sell_date = candle.date

                    position.sell_price = candle.close



                    #
                    # 자산 반영
                    #
                    capital *= (

                        1

                        +

                        position.return_rate / 100

                    )


                    trades.append(

                        position

                    )


                    print(

                        "CLOSE:",

                        reason,

                        candle.date,

                        candle.close,

                        f"{position.return_rate:.2f}%"

                    )


                    position = None



        #
        # 마지막 강제 청산
        #
        if position is not None:


            last = series.candles[-1]


            position.sell_date = last.date

            position.sell_price = last.close



            capital *= (

                1

                +

                position.return_rate / 100

            )


            trades.append(

                position

            )


            print(

                "FORCE CLOSE:",

                last.date,

                last.close,

                f"{position.return_rate:.2f}%"

            )



        #
        # 최종 자산 기록
        #
        equity_history.append(

            {

                "date": series.candles[-1].date,

                "capital": capital

            }

        )


        return BacktestResult(

            trades,

            equity_history

        )