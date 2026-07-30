from datetime import datetime

from backtest.model.selection import Selection
from ranking.ranking_result import RankingResult


class SelectionEngine:
    """Creates a dated selection snapshot from a ranking result."""

    def select(
        self,
        ranking: RankingResult,
        selected_date: datetime,
        top_n: int = 5,
    ) -> list[Selection]:
        if top_n <= 0:
            raise ValueError("top_n must be greater than zero")

        return [
            Selection(
                analysis=item.analysis,
                selected_date=selected_date,
                rank=item.rank,
            )
            for item in ranking.top_n(top_n)
        ]
