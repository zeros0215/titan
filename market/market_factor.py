"""
Market Factor
"""

from dataclasses import dataclass


@dataclass(slots=True)
class MarketFactor:

    trend: int = 0

    volume: int = 0

    volatility: int = 0

    breadth: int = 0

    confidence: int = 0

    total: int = 0