from prediction.prediction_grade import PredictionGrade
from prediction.prediction_result import PredictionResult

from scoring.score_result import ScoreResult
from config.selection_criteria import SELECTION_CRITERIA


class PredictionEngine:

    _BUY_SCORE = SELECTION_CRITERIA.buy_score
    _WATCH_SCORE = SELECTION_CRITERIA.watch_score
    _HOLD_SCORE = 40

    def __init__(self, criteria=SELECTION_CRITERIA):
        self._BUY_SCORE = criteria.buy_score
        self._WATCH_SCORE = criteria.watch_score

    def predict(
        self,
        score: ScoreResult
    ) -> PredictionResult:

        total = score.normalized_score

        if total >= self._BUY_SCORE:

            return PredictionResult(
                total_score=total,
                confidence=0.80,
                expected_return=0.08,
                grade=PredictionGrade.BUY
            )

        if total >= self._WATCH_SCORE:

            return PredictionResult(
                total_score=total,
                confidence=0.70,
                expected_return=0.06,
                grade=PredictionGrade.WATCH
            )

        if total >= self._HOLD_SCORE:

            return PredictionResult(
                total_score=total,
                confidence=0.50,
                expected_return=0.03,
                grade=PredictionGrade.HOLD
            )

        return PredictionResult(
            total_score=total,
            confidence=0.20,
            expected_return=0.00,
            grade=PredictionGrade.PASS
        )
