"""
Market Regime
"""

from dataclasses import dataclass

from market.signal import MarketSignal

from market.market_factor import MarketFactor


@dataclass(slots=True)
class MarketRegime:

    signal: MarketSignal

    factor: MarketFactor

    confidence: int

    reason: str