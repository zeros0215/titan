"""
TITAN Backtest Performance Score
"""


class PerformanceScore:


    def calculate(

        self,

        result

    ):


        score = 0


        #
        # 거래 없음
        #
        if result.total_trades == 0:

            return 0



        ret = result.total_return

        pf = result.profit_factor

        win = result.win_rate

        mdd = result.max_drawdown

        trades = result.total_trades



        #
        # =========================
        # Return Score (30)
        # =========================
        #
        if ret >= 30:

            score += 30


        elif ret >= 20:

            score += 25


        elif ret >= 10:

            score += 20


        elif ret >= 5:

            score += 15


        elif ret > 0:

            score += 5




        #
        # =========================
        # Profit Factor (20)
        # =========================
        #
        # 거래수가 적은 PF 과대평가 방지
        #
        if pf == float("inf"):


            if trades >= 10:

                score += 20


            elif trades >= 5:

                score += 15


            elif trades >= 3:

                score += 10


            else:

                score += 5



        else:


            if trades < 5:


                if pf >= 3:

                    score += 10


                elif pf >= 2:

                    score += 7


                elif pf >= 1.5:

                    score += 5



            else:


                if pf >= 3:

                    score += 20


                elif pf >= 2:

                    score += 15


                elif pf >= 1.5:

                    score += 10


                elif pf >= 1:

                    score += 5





        #
        # =========================
        # Win Rate (10)
        # =========================
        #
        if win >= 70:

            score += 10


        elif win >= 50:

            score += 7


        elif win >= 30:

            score += 3





        #
        # =========================
        # MDD Risk (20)
        # =========================
        #
        #
        # MDD Risk
        #
        if ret <= 0:

            pass

        else:

            if mdd >= -2:
                score +=20

            elif mdd >= -5:
                score +=15

            elif mdd >= -8:
                score +=10

            elif mdd >= -12:
                score +=5





        #
        # =========================
        # Trade Reliability (10)
        # =========================
        #

        if trades >= 20:

            score += 10


        elif trades >= 10:

            score += 8


        elif trades >= 5:

            score += 5


        elif trades >= 3:

            score += 3


        elif trades < 3:

            score -= 5





        #
        # =========================
        # Risk Reward (10)
        # =========================
        #
        if mdd != 0:


            risk_reward = (

                ret

                /

                abs(mdd)

            )


            if risk_reward >= 3:

                score += 10


            elif risk_reward >= 2:

                score += 7


            elif risk_reward >= 1:

                score += 5


            elif risk_reward > 0:

                score += 2





        #
        # =========================
        # Negative Return Penalty
        # =========================
        #
        # 손실 규모별 차등 감점
        #
        if ret <= -20:

            score -=20


        elif ret <= -10:

            score -=15


        elif ret <= -3:

            score -=10


        elif ret < 0:

            score -=2





        #
        # =========================
        # Score Range
        # =========================
        #
        return max(

            min(

                score,

                100

            ),

            1

        )