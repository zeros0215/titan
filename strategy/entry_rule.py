"""
TITAN Entry Rule
"""


class EntryRule:


    BUY_SCORE = 60
    SELL_SCORE = 35


    def should_enter(

        self,

        score

    ):


        if score.normalized_score >= self.BUY_SCORE:

            return True


        return False