from domain.candle_series import CandleSeries
from indicators.moving_average_result import MovingAverageResult


class MovingAverageCalculator:

    @staticmethod
    def calculate(series: CandleSeries) -> MovingAverageResult:

        closes = series.closes

        if len(closes) < 61:
            raise ValueError("Need at least 61 candles.")

        def average(period: int, offset: int = 0):

            end = len(closes) - offset

            start = end - period

            values = closes[start:end]

            return sum(values) / period

        return MovingAverageResult(
            ma5=average(5),
            ma20=average(20),
            ma60=average(60),

            prev_ma5=average(5, 1),
            prev_ma20=average(20, 1),
            prev_ma60=average(60, 1),
        )