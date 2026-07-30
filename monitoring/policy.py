from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MonitoringPolicy:
    recent_run_count: int = 10
    minimum_sample_size: int = 30
    watch_win_rate_drop: float = 0.08
    alert_win_rate_drop: float = 0.15
    watch_excess_return_drop: float = 0.015
    alert_excess_return_drop: float = 0.03
    absolute_alert_win_rate: float = 0.40
    absolute_alert_excess_return: float = -0.03

    def __post_init__(self) -> None:
        if self.recent_run_count <= 0:
            raise ValueError("recent_run_count must be greater than zero")
        if self.minimum_sample_size <= 0:
            raise ValueError("minimum_sample_size must be greater than zero")
