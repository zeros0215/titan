"""
Momentum Factor
"""


class MomentumFactor:

    def calculate(self, feature) -> int:

        score = 0

        #
        # 5일 모멘텀
        #
        if feature.momentum5 >= 5:
            score += 50

        elif feature.momentum5 >= 2:
            score += 30

        #
        # 20일 모멘텀
        #
        if feature.momentum20 >= 10:
            score += 50

        elif feature.momentum20 >= 5:
            score += 30

        return min(score, 100)