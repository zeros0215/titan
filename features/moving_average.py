"""
Moving Average
"""


class MovingAverage:

    @staticmethod
    def calculate(values: list[float], period: int) -> float:

        if len(values) < period:
            return 0.0

        return sum(values[-period:]) / period