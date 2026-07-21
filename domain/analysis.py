"""
Analysis Result
"""

from dataclasses import dataclass, field

from domain.stock import Stock
from domain.indicator import IndicatorResult
from domain.signal import SignalResult
from domain.score import ScoreResult


@dataclass(slots=True)
class AnalysisResult:

    stock: Stock

    current_price: float

    indicator: IndicatorResult

    signal: SignalResult

    score: ScoreResult

    reasons: list[str] = field(default_factory=list)

    def add_reason(self, text: str) -> None:
        self.reasons.append(text)