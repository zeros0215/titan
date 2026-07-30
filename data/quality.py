from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from domain.candle_series import CandleSeries


class DataQualitySeverity(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(slots=True, frozen=True)
class DataQualityIssue:
    code: str
    severity: DataQualitySeverity
    message: str


@dataclass(slots=True, frozen=True)
class SeriesQualityResult:
    series: CandleSeries
    issues: list[DataQualityIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(
            issue.severity is DataQualitySeverity.ERROR
            for issue in self.issues
        )

    @property
    def has_warnings(self) -> bool:
        return any(
            issue.severity is DataQualitySeverity.WARNING
            for issue in self.issues
        )


@dataclass(slots=True, frozen=True)
class DataQualitySummary:
    total_count: int
    valid_count: int
    warning_count: int
    excluded_count: int
    issues_by_code: dict[str, int] = field(default_factory=dict)
    issues_by_stock: dict[str, list[DataQualityIssue]] = field(default_factory=dict)

    @classmethod
    def from_results(
        cls,
        results: dict[str, SeriesQualityResult],
    ) -> "DataQualitySummary":
        counts = Counter(
            issue.code
            for result in results.values()
            for issue in result.issues
        )
        return cls(
            total_count=len(results),
            valid_count=sum(result.is_valid for result in results.values()),
            warning_count=sum(
                result.is_valid and result.has_warnings
                for result in results.values()
            ),
            excluded_count=sum(
                not result.is_valid for result in results.values()
            ),
            issues_by_code=dict(sorted(counts.items())),
            issues_by_stock={
                code: result.issues
                for code, result in results.items()
                if result.issues
            },
        )


class CandleSeriesValidator:
    """Normalize safe structural issues and reject invalid OHLCV."""

    def __init__(
        self,
        minimum_candles: int = 61,
        extreme_return: float = 0.5,
        repeated_candles: int = 10,
    ) -> None:
        self.minimum_candles = minimum_candles
        self.extreme_return = extreme_return
        self.repeated_candles = repeated_candles

    def validate(self, series: CandleSeries) -> SeriesQualityResult:
        issues: list[DataQualityIssue] = []
        original = series.candles
        if not original:
            return SeriesQualityResult(series, [
                self._error("EMPTY_SERIES", "no candles available")
            ])

        if original != sorted(original, key=lambda candle: candle.date):
            issues.append(self._warning(
                "UNSORTED_DATES",
                "candles were sorted by date",
            ))
        by_date = {candle.date: candle for candle in original}
        if len(by_date) != len(original):
            issues.append(self._warning(
                "DUPLICATE_DATES",
                "duplicate dates were merged using the latest candle",
            ))
        candles = sorted(by_date.values(), key=lambda candle: candle.date)
        cleaned = CandleSeries(series.stock, candles)

        if len(candles) < self.minimum_candles:
            issues.append(self._error(
                "INSUFFICIENT_HISTORY",
                f"requires {self.minimum_candles} candles, got {len(candles)}",
            ))

        for candle in candles:
            if min(candle.open, candle.high, candle.low, candle.close) <= 0:
                issues.append(self._error(
                    "NON_POSITIVE_PRICE",
                    f"non-positive price at {candle.date.isoformat()}",
                ))
                break
            if candle.volume < 0:
                issues.append(self._error(
                    "NEGATIVE_VOLUME",
                    f"negative volume at {candle.date.isoformat()}",
                ))
                break
            if (
                candle.low > candle.high
                or not candle.low <= candle.open <= candle.high
                or not candle.low <= candle.close <= candle.high
            ):
                issues.append(self._error(
                    "INVALID_OHLC",
                    f"invalid OHLC range at {candle.date.isoformat()}",
                ))
                break

        if self._has_extreme_return(candles):
            issues.append(self._warning(
                "EXTREME_RETURN",
                "large close-to-close move requires corporate-action review",
            ))
        if self._has_long_gap(candles):
            issues.append(self._warning(
                "LONG_GAP",
                "more than seven calendar days between candles",
            ))
        if self._has_repeated_run(candles):
            issues.append(self._warning(
                "REPEATED_CANDLES",
                "identical OHLCV values repeated for an extended run",
            ))
        return SeriesQualityResult(cleaned, issues)

    def _has_extreme_return(self, candles) -> bool:
        return any(
            previous.close > 0
            and abs(current.close / previous.close - 1) >= self.extreme_return
            for previous, current in zip(candles, candles[1:])
        )

    @staticmethod
    def _has_long_gap(candles) -> bool:
        return any(
            (current.date - previous.date).days > 7
            for previous, current in zip(candles, candles[1:])
        )

    def _has_repeated_run(self, candles) -> bool:
        run = 1
        for previous, current in zip(candles, candles[1:]):
            previous_values = (
                previous.open, previous.high, previous.low,
                previous.close, previous.volume,
            )
            current_values = (
                current.open, current.high, current.low,
                current.close, current.volume,
            )
            run = run + 1 if current_values == previous_values else 1
            if run >= self.repeated_candles:
                return True
        return False

    @staticmethod
    def _warning(code: str, message: str) -> DataQualityIssue:
        return DataQualityIssue(code, DataQualitySeverity.WARNING, message)

    @staticmethod
    def _error(code: str, message: str) -> DataQualityIssue:
        return DataQualityIssue(code, DataQualitySeverity.ERROR, message)
