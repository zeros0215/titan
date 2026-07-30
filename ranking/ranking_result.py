from dataclasses import dataclass

from ranking.ranking_item import RankingItem


@dataclass(slots=True, frozen=True)
class RankingResult:

    items: list[RankingItem]

    @property
    def top(self):

        return self.items[0] if self.items else None

    def top_n(
        self,
        n: int,
    ) -> list[RankingItem]:

        return self.items[:n]