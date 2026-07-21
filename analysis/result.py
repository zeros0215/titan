"""
TITAN Analysis Result
"""

from dataclasses import dataclass

from domain.stock import Stock
from indicators.bundle import IndicatorBundle
from scoring.result import ScoreResult


@dataclass(slots=True)
class AnalysisResult:


    stock: Stock


    #
    # Indicator Snapshot
    #
    indicators: IndicatorBundle


    #
    # Score
    #
    score: ScoreResult


    #
    # Recommendation
    #
    recommendation: str


    #
    # Explanation
    #
    positive_factors: list[str]

    negative_factors: list[str]