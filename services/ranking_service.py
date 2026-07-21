"""
Ranking Service
"""

from ranking.ranking import Ranking


class RankingService:

    def ranking(

        self,

        items

    ):

        return Ranking.sort(

            items

        )