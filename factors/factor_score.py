"""
Factor Score
"""

from dataclasses import dataclass


@dataclass(slots=True)
class FactorScore:

    trend: int = 0

    momentum: int = 0

    volume: int = 0

    breakout: int = 0

    risk: int = 0

    total: int = 0