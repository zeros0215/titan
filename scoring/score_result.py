from dataclasses import dataclass

from scoring.score_constants import ScoreConstants


@dataclass(slots=True, frozen=True)
class ScoreResult:
    """
    최종 점수 결과

    각 Policy에서 계산된 점수를 보관한다.

    total_score
        Raw Score

    normalized_score
        100점 기준 환산 점수
    """

    trend_score: int = 0
    momentum_score: int = 0
    volume_score: int = 0
    price_action_score: int = 0
    risk_score: int = 0
    context_score: int = 0

    @property
    def total_score(self) -> int:
        """
        Raw Score
        """
        return (
            self.trend_score
            + self.momentum_score
            + self.volume_score
            + self.price_action_score
            + self.risk_score
            + self.context_score
        )

    @property
    def normalized_score(self) -> int:
        """
        100점 기준 환산 점수
        """
        return round(
            self.total_score * 100 / ScoreConstants.MAX_SCORE
        )