from dataclasses import dataclass

from prediction.prediction_grade import PredictionGrade


@dataclass(slots=True, frozen=True)
class PredictionValidation:
    """Performance grouped by the analysis prediction grade."""

    grade: PredictionGrade
    total_count: int
    success_count: int
    average_return: float

    @property
    def win_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0
