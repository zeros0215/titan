class LiquidityFilter:

    MIN_VALUE = 2_000_000_000

    def check(self, series):

        value = (

            series.latest.close

            *

            series.latest.volume

        )

        return value >= self.MIN_VALUE