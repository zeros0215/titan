from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class StrategyGatePolicy:
    minimum_folds: int = 2
    minimum_samples: int = 100
    minimum_completion_rate: float = 0.80
    minimum_net_return_improvement: float = 0.005
    minimum_excess_return_improvement: float = 0.005
    minimum_positive_fold_ratio: float = 2 / 3
    require_complete_universe: bool = True
    require_zero_errors: bool = True
