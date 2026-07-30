"""
Ranking Engine
"""


class Ranker:

    def rank(

        self,

        results

    ):

        return sorted(

            results,

            key=lambda x: x.score.total_score,

            reverse=True

        )