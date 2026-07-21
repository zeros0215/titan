"""
Trend Factor
"""


class TrendFactor:

    def calculate(self, feature) -> int:

        score = 0

        #
        # 이동평균 정배열
        #
        if feature.ma5 > feature.ma20:
            score += 30

        if feature.ma20 > feature.ma60:
            score += 30

        if feature.ma60 > feature.ma120:
            score += 20

        #
        # 현재가 위치
        #
        if feature.close > feature.ma20:
            score += 20

        return min(score, 100)