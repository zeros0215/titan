from dataclasses import dataclass


@dataclass(frozen=True)
class MovingAverageResult:
    """
    이동평균 계산 결과
    """

    ma5: float
    ma20: float
    ma60: float

    prev_ma5: float
    prev_ma20: float
    prev_ma60: float