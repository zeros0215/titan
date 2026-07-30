from dataclasses import dataclass

from feature.feature_type import FeatureType


@dataclass(slots=True, frozen=True)
class FeatureValidation:
    """Performance of selections where one enabled feature was present."""

    feature_type: FeatureType
    total_count: int
    success_count: int
    average_return: float
    average_gross_return: float | None = None
    average_benchmark_return: float | None = None
    average_excess_return: float | None = None

    @property
    def win_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0

    @property
    def effective_gross_return(self) -> float:
        return (
            self.average_gross_return
            if self.average_gross_return is not None
            else self.average_return
        )
