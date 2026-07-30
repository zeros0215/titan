"""
Ranking Engine
"""

from analysis.analysis_result import AnalysisResult

from ranking.ranking_item import RankingItem
from ranking.ranking_result import RankingResult
from ranking.ranking_policy import RankingPolicy


class RankingEngine:

    def __init__(
        self,
        policy: RankingPolicy | None = None,
    ):

        self.policy = policy or RankingPolicy()

    def rank(
        self,
        analyses: list[AnalysisResult],
    ) -> RankingResult:

        ordered = sorted(
            analyses,
            key=self.policy.sort_key,
        )

        items = [
            RankingItem(
                rank=index,
                analysis=analysis,
            )
            for index, analysis in enumerate(
                ordered,
                start=1,
            )
        ]

        return RankingResult(items)
