from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ScoreBand:
    minimum: int
    maximum: int

    @property
    def label(self) -> str:
        return f"{self.minimum}-{self.maximum}"


SCORE_BANDS = (
    ScoreBand(0, 59),
    ScoreBand(60, 69),
    ScoreBand(70, 79),
    ScoreBand(80, 89),
    ScoreBand(90, 100),
)


def score_band_for(score: int) -> ScoreBand:
    for band in SCORE_BANDS:
        if band.minimum <= score <= band.maximum:
            return band
    raise ValueError(f"normalized score must be between 0 and 100: {score}")


@dataclass(slots=True, frozen=True)
class ScoreBandValidation:
    minimum_score: int
    maximum_score: int
    total_count: int
    success_count: int
    average_return: float
    average_gross_return: float
    average_benchmark_return: float | None = None
    average_excess_return: float | None = None

    @property
    def label(self) -> str:
        return f"{self.minimum_score}-{self.maximum_score}"

    @property
    def win_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0


def assess_score_monotonicity(
    validations: list[ScoreBandValidation],
    minimum_sample_size: int = 30,
) -> str:
    eligible = [
        item for item in validations if item.total_count >= minimum_sample_size
    ]
    if len(eligible) < 2:
        return "INSUFFICIENT_DATA"
    win_rates = [item.win_rate for item in eligible]
    return (
        "MONOTONIC"
        if all(left <= right for left, right in zip(win_rates, win_rates[1:]))
        else "NON_MONOTONIC"
    )
