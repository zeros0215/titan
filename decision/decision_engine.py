"""
Decision Engine
"""

from prediction.prediction_grade import PredictionGrade
from prediction.prediction_result import PredictionResult

from decision.decision_result import DecisionResult
from decision.decision_type import DecisionType


class DecisionEngine:
    """
    Prediction 결과를 최종 투자 의사결정으로 변환한다.
    """

    def decide(
        self,
        prediction: PredictionResult,
    ) -> DecisionResult:

        grade = prediction.grade

        if grade == PredictionGrade.STRONG_BUY:
            return DecisionResult(
                decision=DecisionType.BUY,
                prediction_grade=grade,
                reason="강한 매수 신호"
            )

        if grade == PredictionGrade.BUY:
            return DecisionResult(
                decision=DecisionType.BUY,
                prediction_grade=grade,
                reason="매수 가능"
            )

        if grade == PredictionGrade.WATCH:
            return DecisionResult(
                decision=DecisionType.WATCH,
                prediction_grade=grade,
                reason="관찰 필요"
            )

        return DecisionResult(
            decision=DecisionType.PASS,
            prediction_grade=grade,
            reason="매수 제외"
        )