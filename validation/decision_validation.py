from dataclasses import dataclass

from decision.decision_type import DecisionType


@dataclass(slots=True, frozen=True)
class DecisionValidation:
    """Performance grouped by the final selection decision."""

    decision: DecisionType
    total_count: int
    success_count: int
    average_return: float

    @property
    def win_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0
