from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ReportResult:
    """
    분석 결과 보고서
    """

    rank: int

    code: str
    name: str

    score: float

    prediction: str
    decision: str

    confidence: float
    expected_return: float

    positive_factors: list[str]
    negative_factors: list[str]