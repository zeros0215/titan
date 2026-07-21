"""
TITAN Score Strategy
"""


from indicators.calculator import IndicatorCalculator
from scoring.engine import ScoreEngine

from strategy.entry_rule import EntryRule



class TitanScoreStrategy:


    DEBUG = False



    def __init__(self):


        self.indicator_calculator = (
            IndicatorCalculator()
        )


        self.score_engine = (
            ScoreEngine()
        )


        self.entry_rule = (
            EntryRule()
        )


        #
        # 마지막 Score Cache
        #
        self.last_score = None



    def evaluate(

        self,

        series

    ):


        score = self.get_score(series)



        if self.DEBUG:


            print(

                f"{series.stock.code} "

                f"SCORE={score.normalized_score}"

            )



        #
        # Entry
        #
        if self.entry_rule.should_enter(score):


            print(
                "SIGNAL : BUY"
            )


            return "BUY"



        print(
            "SIGNAL : HOLD"
        )


        return "HOLD"




    def get_score(

        self,

        series

    ):


        indicators = (

            self.indicator_calculator.calculate(

                series

            )

        )


        score = (

            self.score_engine.calculate(

                indicators

            )

        )


        self.last_score = score


        return score