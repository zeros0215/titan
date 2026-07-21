"""
Risk Factor
"""


class RiskFactor:

    def calculate(self, feature) -> int:

        atr = feature.atr14

        if feature.close == 0:
            return 0

        atr_ratio = atr / feature.close

        #
        # ATR이 작을수록 안정적
        #
        if atr_ratio <= 0.01:
            return 100

        if atr_ratio <= 0.02:
            return 80

        if atr_ratio <= 0.03:
            return 60

        if atr_ratio <= 0.05:
            return 40

        return 20