from dataclasses import dataclass

from prediction.prediction_grade import PredictionGrade


@dataclass(slots=True)
class PredictionResult:

    total_score: int

    confidence: float

    grade: PredictionGrade

    expected_return: float