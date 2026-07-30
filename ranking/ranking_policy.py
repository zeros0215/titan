"""
Ranking Policy
"""

from analysis.analysis_result import AnalysisResult
from decision.decision_type import DecisionType


class RankingPolicy:
    """
    Ranking 정렬 정책
    """

    _DECISION_PRIORITY = {
        DecisionType.BUY: 3,
        DecisionType.WATCH: 2,
        DecisionType.PASS: 1,
    }

    def sort_key(
        self,
        analysis: AnalysisResult,
    ) -> tuple:
        indicators = getattr(analysis, "indicators", None)
        volume = getattr(indicators, "volume", None)
        trading_value = float(
            getattr(volume, "current_trading_value", 0.0)
        )
        return (
            -self._DECISION_PRIORITY[
                analysis.decision.decision
            ],
            -analysis.score.normalized_score,
            -trading_value,
            analysis.code,
        )
