from dataclasses import dataclass, field
from pathlib import Path

from backtest.model.selection import Selection
from domain.candle_series import CandleSeries
from ranking.ranking_result import RankingResult
from data.quality import DataQualitySummary
from repository.universe_snapshot import UniverseSnapshot


@dataclass(slots=True, frozen=True)
class SelectionRunResult:
    """Artifacts from a point-in-time candidate selection run."""

    ranking: RankingResult
    selections: list[Selection]
    series_by_code: dict[str, CandleSeries]
    snapshot_path: Path | None
    observations: list[Selection] = field(default_factory=list)
    observation_snapshot_path: Path | None = None
    quality_summary: DataQualitySummary | None = None
    quality_report_path: Path | None = None
    universe_snapshot: UniverseSnapshot | None = None
    universe_report_path: Path | None = None
    fetch_failures: dict[str, str] = field(default_factory=dict)
