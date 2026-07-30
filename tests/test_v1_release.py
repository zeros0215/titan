import json
import tempfile
import unittest
from pathlib import Path

from release.v1 import backtest_preflight, freeze_v1, spec_hash


class V1ReleaseTest(unittest.TestCase):
    def test_freeze_is_idempotent_and_hash_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.json"
            first, digest = freeze_v1(path)
            second, second_digest = freeze_v1(path)

            spec = {
                key: value for key, value in first.items()
                if key not in {"frozen_at", "config_sha256"}
            }
            self.assertEqual(digest, spec_hash(spec))
            self.assertEqual(digest, second_digest)
            self.assertEqual(first, second)

    def test_preflight_blocks_incomplete_universe_and_zero_costs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec_path = root / "v1.json"
            freeze_v1(spec_path)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({"point_in_time_complete": False, "notes": "current"}),
                encoding="utf-8",
            )
            stocks = root / "stocks.csv"
            stocks.write_text("code,name,market\n005930,Samsung,KOSPI\n", encoding="utf-8")

            result = backtest_preflight(
                spec_path, manifest, stocks, root / "market_data"
            )

            self.assertEqual("BLOCKED", result.status)
            failed = {name for name, passed, _ in result.checks if not passed}
            self.assertIn("point_in_time_universe", failed)
            self.assertIn("minimum_universe_size", failed)
            self.assertIn("minimum_price_history", failed)
            self.assertIn("adjusted_price_evidence", failed)


if __name__ == "__main__":
    unittest.main()
