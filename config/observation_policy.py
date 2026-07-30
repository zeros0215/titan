from dataclasses import dataclass
from datetime import datetime

from backtest.model.selection import Selection


@dataclass(slots=True, frozen=True)
class ObservationPolicy:
    """Bounded shadow cohort; never changes candidate eligibility."""

    minimum_score: int = 70
    maximum_score: int = 79
    daily_limit: int = 5

    def select(self, analyses: list, selected_at: datetime) -> list[Selection]:
        if self.daily_limit <= 0:
            return []
        eligible = [
            item
            for item in analyses
            if self.minimum_score
            <= item.score.normalized_score
            <= self.maximum_score
        ]
        ordered = sorted(
            eligible,
            key=lambda item: (
                item.score.normalized_score,
                self._trading_value(item),
                item.code,
            ),
            reverse=True,
        )
        return [
            Selection(analysis=item, selected_date=selected_at, rank=index)
            for index, item in enumerate(
                ordered[:self.daily_limit],
                start=1,
            )
        ]

    @staticmethod
    def _trading_value(analysis) -> float:
        indicators = getattr(analysis, "indicators", None)
        volume = getattr(indicators, "volume", None)
        return float(getattr(volume, "current_trading_value", 0.0))
