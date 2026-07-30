from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MonitorStatus(str, Enum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    ALERT = "ALERT"


@dataclass(slots=True, frozen=True)
class KpiMetrics:
    run_count: int
    sample_count: int
    win_rate: float
    average_net_return: float
    average_benchmark_return: float | None
    average_excess_return: float | None


@dataclass(slots=True, frozen=True)
class HorizonKpi:
    holding_days: int
    status: MonitorStatus
    data_state: str
    recent: KpiMetrics
    baseline: KpiMetrics
    win_rate_delta: float | None = None
    excess_return_delta: float | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class OperationKpi:
    run_count: int
    completed_count: int
    partial_count: int
    failed_count: int
    failure_rate: float


@dataclass(slots=True, frozen=True)
class DataQualityKpi:
    run_count: int
    total_count: int
    valid_count: int
    warning_count: int
    excluded_count: int
    warning_rate: float
    exclusion_rate: float


@dataclass(slots=True, frozen=True)
class MonitoringSnapshot:
    generated_at: datetime
    status: MonitorStatus
    data_state: str
    cumulative: KpiMetrics
    recent: KpiMetrics
    baseline: KpiMetrics
    horizons: list[HorizonKpi]
    operation: OperationKpi
    data_quality: DataQualityKpi
    reasons: list[str]
    context_rows: list[object] = field(default_factory=list)
    feature_rows: list[object] = field(default_factory=list)
    score_band_rows: list[object] = field(default_factory=list)
