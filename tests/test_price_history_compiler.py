import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from price_history.compiler import PriceHistoryCompiler, PriceHistoryLoader


class PriceHistoryCompilerTest(unittest.TestCase):
    def test_compiles_adjusted_prices_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "prices.csv"
            source.write_text(
                "code,name,market,date,open,high,low,close,volume,adjusted\n"
                "005930,Samsung,KOSPI,2022-01-03,100,110,90,105,1000,true\n"
                "005930,Samsung,KOSPI,2022-01-04,105,115,100,110,1200,true\n",
                encoding="utf-8",
            )
            output = root / "staging"
            manifest = PriceHistoryCompiler().compile(
                PriceHistoryLoader().load(source),
                {
                    "source_name": "official",
                    "source_type": "official_adjusted_daily_prices",
                    "dataset_id": "dataset-1",
                    "evidence_url": "https://example.test",
                    "acquired_at": "2026-07-28T00:00:00+09:00",
                    "source_complete": True,
                },
                date(2022, 1, 3),
                date(2022, 1, 4),
                output,
                source,
            )

            payload = json.loads(
                (output / "005930.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["adjusted_prices"])
            self.assertEqual(2, manifest["row_count"])

    def test_rejects_unadjusted_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            path.write_text(
                "code,name,market,date,open,high,low,close,volume,adjusted\n"
                "005930,Samsung,KOSPI,2022-01-03,100,110,90,105,1000,false\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unadjusted"):
                PriceHistoryCompiler().compile(
                    PriceHistoryLoader().load(path),
                    {
                        "source_name": "official",
                        "source_type": "official",
                        "dataset_id": "id",
                        "evidence_url": "https://example.test",
                        "acquired_at": "2026-07-28",
                        "source_complete": True,
                    },
                    date(2022, 1, 3),
                    date(2022, 1, 3),
                    Path(directory) / "out",
                    path,
                )


if __name__ == "__main__":
    unittest.main()
