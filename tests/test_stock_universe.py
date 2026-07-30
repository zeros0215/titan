from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from repository.stock_repository import StockRepository
from repository.universe_repository import UniverseRepository
from repository.universe_snapshot import UniverseCoverage
from report.report_generator import ReportGenerator


class StockUniverseTest(unittest.TestCase):
    def test_filters_records_by_effective_dates(self) -> None:
        with TemporaryDirectory() as directory:
            market_dir = Path(directory)
            self._write(
                market_dir / "kospi.csv",
                [
                    "code,name,market,effective_from,effective_to",
                    "A,Active,KOSPI,2020-01-01,",
                    "B,Future,KOSPI,2027-01-01,",
                    "C,Delisted,KOSPI,2010-01-01,2025-12-31",
                ],
            )
            self._write(
                market_dir / "kosdaq.csv",
                ["code,name,market,effective_from,effective_to"],
            )
            (market_dir / "universe_manifest.json").write_text(
                json.dumps({"point_in_time_complete": True}),
                encoding="utf-8",
            )

            snapshot = StockRepository(market_dir).get_as_of(
                datetime(2026, 1, 2)
            )

        self.assertEqual([stock.code for stock in snapshot.stocks], ["A"])
        self.assertEqual(snapshot.excluded_before_listing, 1)
        self.assertEqual(snapshot.excluded_after_delisting, 1)
        self.assertEqual(snapshot.coverage, UniverseCoverage.COMPLETE)

    def test_marks_current_only_sources_as_unknown(self) -> None:
        with TemporaryDirectory() as directory:
            market_dir = Path(directory)
            self._write(
                market_dir / "kospi.csv",
                ["code,name,market", "A,Unknown,KOSPI"],
            )
            self._write(
                market_dir / "kosdaq.csv",
                ["code,name,market"],
            )
            snapshot = StockRepository(market_dir).get_as_of(
                datetime(2020, 1, 2)
            )
            path = UniverseRepository(
                market_dir / "output"
            ).save(snapshot)

        report = ReportGenerator().generate_selection_markdown(
            [],
            universe_snapshot=snapshot,
        )
        self.assertEqual(snapshot.coverage, UniverseCoverage.UNKNOWN)
        self.assertEqual(snapshot.unknown_date_count, 1)
        self.assertTrue(path.name.endswith(".json"))
        self.assertIn("survivorship bias may remain", report)

    @staticmethod
    def _write(path: Path, lines: list[str]) -> None:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
