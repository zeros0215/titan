from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class SelectionSnapshot:
    """Persistable record of why a stock was selected at a point in time."""

    selected_at: datetime
    rank: int
    code: str
    name: str
    total_score: int
    normalized_score: int
    trend_score: int
    momentum_score: int
    volume_score: int
    price_action_score: int
    risk_score: int
    context_score: int
    enabled_features: list[str]
    prediction_grade: str | None
    decision: str | None
    positive_factors: list[str]
    negative_factors: list[str]
    market: str | None = None
    market_context: dict[str, str | float | int] | None = None
