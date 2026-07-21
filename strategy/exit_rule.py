"""
TITAN Exit Rule
"""


class ExitRule:


    STOP_LOSS = -8.0


    TAKE_PROFIT = 15.0


    SCORE_EXIT = 25



    def should_exit(

        self,

        trade,

        score

    ):


        #
        # 1. 손절
        #
        if trade.return_rate <= self.STOP_LOSS:


            return (

                True,

                "STOP LOSS"

            )



        #
        # 2. 위험 증가
        #
        if score.risk_penalty >= 10:


            return (

                True,

                "RISK"

            )



        #
        # 3. Score 붕괴
        #
        if score.normalized_score <= self.SCORE_EXIT:


            return (

                True,

                "SCORE DROP"

            )



        #
        # 4. 익절
        #
        if trade.return_rate >= self.TAKE_PROFIT:


            return (

                True,

                "TAKE PROFIT"

            )



        return (

            False,

            None

        )