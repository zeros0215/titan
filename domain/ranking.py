"""
Ranking Domain Model
"""

from dataclasses import dataclass

from domain.analysis import AnalysisResult


@dataclass(slots=True)
class RankingItem:

    rank: int

    result: AnalysisResult