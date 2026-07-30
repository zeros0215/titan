from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BreakoutResult:
    """
    돌파(Price Position) 관련 지표
    """

    # 현재가 / 최근 20일 최고가
    position20: float

    # 현재가 / 최근 60일 최고가
    position60: float