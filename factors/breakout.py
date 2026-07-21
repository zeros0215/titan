"""
Breakout Factor
"""


class BreakoutFactor:

    def calculate(self, feature) -> int:

        #
        # 신고가 돌파
        #
        if feature.close >= feature.highest20:

            return 100

        diff = (

            feature.highest20

            - feature.close

        ) / feature.highest20

        if diff <= 0.02:
            return 80

        if diff <= 0.05:
            return 50

        return 20