from datetime import datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.quality import CandleSeriesValidator, DataQualitySeverity
from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.enums import MarketType
from domain.stock import Stock
from data.quality import DataQualitySummary
from repository.data_quality_repository import DataQualityRepository
from report.report_generator import ReportGenerator


class CandleSeriesValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stock = Stock("000001", "Alpha", MarketType.KOSPI)

    def test_normalizes_sorting_and_duplicate_dates_with_warnings(self) -> None:
        start = datetime(2026, 1, 1)
        series = CandleSeries(self.stock, [
            self._candle(start + timedelta(days=1), 101),
            self._candle(start, 100),
            self._candle(start, 102),
        ])

        result = CandleSeriesValidator(minimum_candles=2).validate(series)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.series), 2)
        self.assertEqual(result.series.candles[0].close, 102)
        self.assertEqual(
            {issue.code for issue in result.issues},
            {"UNSORTED_DATES", "DUPLICATE_DATES"},
        )

    def test_rejects_invalid_ohlcv(self) -> None:
        candle = Candle(
            datetime(2026, 1, 1),
            open=110,
            high=100,
            low=90,
            close=95,
            volume=1_000,
        )

        result = CandleSeriesValidator(minimum_candles=1).validate(
            CandleSeries(self.stock, [candle])
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.issues[0].code, "INVALID_OHLC")
        self.assertEqual(result.issues[0].severity, DataQualitySeverity.ERROR)

    def test_warns_on_extreme_returns_without_silently_excluding(self) -> None:
        start = datetime(2026, 1, 1)
        result = CandleSeriesValidator(minimum_candles=2).validate(
            CandleSeries(self.stock, [
                self._candle(start, 100),
                self._candle(start + timedelta(days=1), 160),
            ])
        )

        self.assertTrue(result.is_valid)
        self.assertIn("EXTREME_RETURN", [issue.code for issue in result.issues])

    def test_rejects_insufficient_history(self) -> None:
        result = CandleSeriesValidator(minimum_candles=61).validate(
            CandleSeries(
                self.stock,
                [self._candle(datetime(2026, 1, 1), 100)],
            )
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.issues[0].code, "INSUFFICIENT_HISTORY")

    def test_persists_and_reports_quality_summary(self) -> None:
        summary = DataQualitySummary(
            total_count=10,
            valid_count=8,
            warning_count=1,
            excluded_count=2,
            issues_by_code={"INVALID_OHLC": 2, "LONG_GAP": 1},
        )
        selected_at = datetime(2026, 1, 2)
        with TemporaryDirectory() as directory:
            path = DataQualityRepository(Path(directory)).save(
                selected_at,
                summary,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        report = ReportGenerator().generate_selection_markdown(
            [],
            quality_summary=summary,
        )
        self.assertEqual(payload["excluded_count"], 2)
        self.assertEqual(payload["issues_by_code"]["INVALID_OHLC"], 2)
        self.assertIn("## Data quality", report)
        self.assertIn("| INVALID_OHLC | 2 |", report)

    @staticmethod
    def _candle(date: datetime, close: float) -> Candle:
        return Candle(date, close, close, close, close, 1_000)


if __name__ == "__main__":
    unittest.main()
