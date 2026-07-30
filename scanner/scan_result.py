from dataclasses import dataclass
from dataclasses import field

from analysis.analysis_result import AnalysisResult
from domain.candle_series import CandleSeries
from data.quality import DataQualitySummary


@dataclass(slots=True, frozen=True)
class ScanResult:
    """Analysis outputs together with the market data used to create them."""

    analyses: list[AnalysisResult]
    series_by_code: dict[str, CandleSeries]
    quality_summary: DataQualitySummary | None = None
    fetch_failures: dict[str, str] = field(default_factory=dict)
