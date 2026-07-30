from __future__ import annotations

from dataclasses import dataclass, field

from validation.decision_validation import DecisionValidation
from validation.feature_validation import FeatureValidation
from validation.prediction_validation import PredictionValidation
from validation.context_validation import ContextValidation
from validation.feature_regime_validation import FeatureRegimeValidation
from validation.score_band_validation import ScoreBandValidation


@dataclass(slots=True)
class ValidationResult:
    """
    Selection 결과에 대한 검증 결과.
    """

    total_count: int

    success_count: int

    fail_count: int

    win_rate: float

    average_return: float

    feature_validations: list[FeatureValidation]

    prediction_validations: list[PredictionValidation]

    decision_validations: list[DecisionValidation]

    average_gross_return: float = 0.0

    average_net_return: float = 0.0

    average_benchmark_return: float | None = None

    average_excess_return: float | None = None

    context_validations: list[ContextValidation] = field(default_factory=list)
    feature_regime_validations: list[FeatureRegimeValidation] = field(
        default_factory=list
    )
    score_band_validations: list[ScoreBandValidation] = field(
        default_factory=list
    )
