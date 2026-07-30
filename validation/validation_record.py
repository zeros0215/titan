from dataclasses import dataclass
from datetime import datetime

from validation.validation_result import ValidationResult


@dataclass(slots=True, frozen=True)
class ValidationRecord:
    """One completed evaluation of a stored selection snapshot."""

    selected_at: datetime
    evaluation_date: datetime
    holding_days: int
    success_return: float
    result: ValidationResult
