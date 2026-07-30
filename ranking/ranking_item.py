from dataclasses import dataclass

from analysis.analysis_result import AnalysisResult


@dataclass(slots=True, frozen=True)
class RankingItem:
    """
    랭킹에 포함되는 단일 종목
    """

    rank: int

    analysis: AnalysisResult