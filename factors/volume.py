"""
Volume Factor
"""


class VolumeFactor:

    def calculate(self, feature) -> int:

        ratio = feature.volume_ratio

        if ratio >= 3:
            return 100

        if ratio >= 2:
            return 80

        if ratio >= 1.5:
            return 60

        if ratio >= 1:
            return 40

        return 10