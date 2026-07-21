"""
TITAN Recommendation Engine
"""


class RecommendationEngine:


    def decide(

        self,

        score,

        indicators

    ):


        #
        # 위험 우선
        #

        if score.risk_penalty >= 20:

            return "AVOID"



        #
        # 강한 상승 조건
        #

        if (

            score.normalized_score >= 80

            and

            score.trend_score >= 30

            and

            score.momentum_score >= 10

        ):

            return "BUY"



        #
        # 관심 종목
        #

        if (

            score.normalized_score >= 60

        ):

            return "WATCH"



        #
        # 유지
        #

        if (

            score.normalized_score >= 40

        ):

            return "HOLD"



        return "AVOID"