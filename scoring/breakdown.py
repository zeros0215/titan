from dataclasses import dataclass


@dataclass(slots=True)
class ScoreBreakdown:

    trend: int

    volume: int

    trading: int

    momentum: int

    breakout: int

    risk: int