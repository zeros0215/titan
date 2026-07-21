"""
Volatility Feature
"""


class VolatilityFeature:

    @staticmethod
    def atr(series, period=14):

        candles = series.candles

        if len(candles) <= period:
            return 0

        tr_sum = 0

        for i in range(-period, 0):

            current = candles[i]

            previous = candles[i - 1]

            tr = max(

                current.high - current.low,

                abs(current.high - previous.close),

                abs(current.low - previous.close)

            )

            tr_sum += tr

        return tr_sum / period