from strategy.base import Strategy



class TrendStrategy(Strategy):


    def evaluate(

        self,

        candle

    ):


        if candle.close > candle.open:

            return "BUY"


        return "SELL"