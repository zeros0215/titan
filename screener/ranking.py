"""
Ranking
"""

from ranking.ranking_item import RankingItem


class Ranking:

    @staticmethod
    def sort(items: list[RankingItem]) -> list[RankingItem]:

        return sorted(

            items,

            key=lambda x: x.strategy.score,

            reverse=True

        )