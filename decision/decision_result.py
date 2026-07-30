from dataclasses import dataclass

from decision.decision_type import DecisionType
from prediction.prediction_grade import PredictionGrade


@dataclass(slots=True, frozen=True)
class DecisionResult:
    """
    최종 투자 의사결정 결과
    """

    decision: DecisionType

    prediction_grade: PredictionGrade

    reason: str