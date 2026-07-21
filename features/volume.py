"""
Volume Feature
"""


class VolumeFeature:

    @staticmethod
    def average(values: list[int], period=20):

        if len(values) < period:
            return 0

        return sum(values[-period:]) / period

    @staticmethod
    def ratio(values: list[int], period=20):

        avg = VolumeFeature.average(values, period)

        if avg == 0:
            return 0

        return values[-1] / avg