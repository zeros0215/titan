"""
Market Feature
"""

from dataclasses import dataclass


@dataclass(slots=True)
class MarketFeature:

    #
    # Index
    #
    close: float

    ma20: float

    ma60: float

    ma120: float

    #
    # Volume
    #
    volume: float

    volume_ma20: float

    volume_ratio: float

    #
    # Volatility
    #
    atr14: float

    #
    # Breadth
    #
    advance_count: int

    decline_count: int

    advance_ratio: float