"""
Strategy Result
"""

from dataclasses import dataclass

from strategy.signal import Signal


@dataclass(slots=True)
class StrategyResult:

    signal: Signal

    score: int

    reason: str