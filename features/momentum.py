"""
Momentum Feature
"""


class MomentumFeature:

    @staticmethod
    def rate(closes: list[float], period: int):

        if len(closes) <= period:
            return 0

        prev = closes[-period]

        if prev == 0:
            return 0

        return (closes[-1] - prev) / prev * 100