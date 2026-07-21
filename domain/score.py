"""
Score Domain Model
"""

from dataclasses import dataclass


@dataclass(slots=True)
class ScoreResult:

    trend_score: int = 0

    volume_score: int = 0

    trading_score: int = 0

    momentum_score: int = 0

    breakout_score: int = 0

    risk_penalty: int = 0

    total_score: int = 0

    grade: str = "D"