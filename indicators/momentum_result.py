from dataclasses import dataclass


@dataclass(frozen=True)
class MomentumResult:
    """
    모멘텀 계산 결과
    """

    momentum_5: float
    momentum_20: float

    acceleration: float