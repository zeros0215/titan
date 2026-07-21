"""
TITAN Ranker
"""


class Ranker:


    def rank(

        self,

        results

    ):


        return sorted(

            results,

            key=self._ranking_key,

            reverse=True

        )


    def _ranking_key(

        self,

        item

    ):


        score = item.score


        return (

            score.normalized_score,

            -score.risk_penalty,

            score.trading_score

        )