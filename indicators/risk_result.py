from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RiskResult:

    change_20d: float