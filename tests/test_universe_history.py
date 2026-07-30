import csv
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from domain.enums import MarketType
from repository.stock_repository import StockRepository
from repository.universe_snapshot import UniverseCoverage
from universe_history.compiler import UniverseHistoryCompiler
from universe_history.loader import UniverseHistoryLoader
from universe_history.model import UniverseHistoryRecord
from universe_history.validator import UniverseHistoryValidator


class UniverseHistoryTest(unittest.TestCase):
    def test_loader_requires_provenance_columns(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "history.csv"
            path.write_text("code,name\n005930,Samsung\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing columns"):
                UniverseHistoryLoader().load(path)

    def test_validator_rejects_overlapping_market_migration(self):
        records = [
            self._record("123456", MarketType.KOSDAQ, "2020-01-01", "2023-06-30"),
            self._record("123456", MarketType.KOSPI, "2023-06-30", None),
        ]

        result = UniverseHistoryValidator().validate(
            records,
            date(2020, 1, 1),
            date(2025, 12, 31),
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            "OVERLAPPING_INTERVALS",
            [item.code for item in result.errors],
        )

    def test_compiled_history_is_complete_only_inside_verified_range(self):
        records = [
            self._record("005930", MarketType.KOSPI, "2020-01-01", None),
            self._record("123456", MarketType.KOSDAQ, "2020-01-01", "2023-06-29"),
            self._record("123456", MarketType.KOSPI, "2023-06-30", None),
        ]
        source = {
            "source_complete": True,
            "coverage_start": "2020-01-01",
            "coverage_end": "2025-12-31",
            "source_name": "fixture",
            "source_type": "official_history",
            "dataset_id": "fixture-001",
            "evidence_url": "https://example.test/dataset",
            "acquired_at": "2026-07-28T00:00:00+09:00",
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            manifest, _ = UniverseHistoryCompiler().compile(
                records,
                source,
                date(2020, 1, 1),
                date(2025, 12, 31),
                output,
                "input-hash",
            )
            inside = StockRepository(output).get_as_of(datetime(2023, 7, 1))
            outside = StockRepository(output).get_as_of(datetime(2019, 12, 31))

        self.assertTrue(manifest["point_in_time_complete"])
        self.assertEqual(UniverseCoverage.COMPLETE, inside.coverage)
        self.assertEqual(
            MarketType.KOSPI,
            next(item for item in inside.stocks if item.code == "123456").market,
        )
        self.assertNotEqual(UniverseCoverage.COMPLETE, outside.coverage)

    def test_compiled_file_tampering_revokes_complete_coverage(self):
        records = [
            self._record("005930", MarketType.KOSPI, "2020-01-01", None),
        ]
        source = {
            "source_complete": True,
            "coverage_start": "2020-01-01",
            "coverage_end": "2025-12-31",
            "source_name": "fixture",
            "source_type": "official_history",
            "dataset_id": "fixture-001",
            "evidence_url": "https://example.test/dataset",
            "acquired_at": "2026-07-28T00:00:00+09:00",
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            UniverseHistoryCompiler().compile(
                records,
                source,
                date(2020, 1, 1),
                date(2025, 12, 31),
                output,
                "input-hash",
            )
            with (output / "kospi.csv").open(
                "a", encoding="utf-8", newline=""
            ) as stream:
                csv.writer(stream).writerow([
                    "999999", "Tampered", "KOSPI", "2020-01-01", "", "x"
                ])

            snapshot = StockRepository(output).get_as_of(datetime(2023, 1, 1))

        self.assertEqual(UniverseCoverage.PARTIAL, snapshot.coverage)
        self.assertFalse(snapshot.point_in_time_complete)

    def test_missing_provenance_cannot_claim_complete(self):
        records = [
            self._record("005930", MarketType.KOSPI, "2020-01-01", None),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            manifest, _ = UniverseHistoryCompiler().compile(
                records,
                {
                    "source_complete": True,
                    "coverage_start": "2020-01-01",
                    "coverage_end": "2025-12-31",
                },
                date(2020, 1, 1),
                date(2025, 12, 31),
                Path(temporary),
                "input-hash",
            )

        self.assertFalse(manifest["point_in_time_complete"])
        self.assertFalse(manifest["provenance_complete"])

    @staticmethod
    def _record(code, market, start, end):
        return UniverseHistoryRecord(
            code=code,
            name=f"Stock {code}",
            market=market,
            effective_from=date.fromisoformat(start),
            effective_to=date.fromisoformat(end) if end else None,
            source_id="fixture",
        )


if __name__ == "__main__":
    unittest.main()
