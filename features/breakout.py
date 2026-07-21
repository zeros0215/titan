"""
Breakout Feature
"""


class BreakoutFeature:

    @staticmethod
    def highest(values, period):

        if len(values) < period:
            return max(values)

        return max(values[-period:])

    @staticmethod
    def lowest(values, period):

        if len(values) < period:
            return min(values)

        return min(values[-period:])