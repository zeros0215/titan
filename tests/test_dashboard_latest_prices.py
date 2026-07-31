import json
import tempfile
import unittest
from pathlib import Path

from tools.build_kis_dashboard import _load_latest_prices


class DashboardLatestPricesTest(unittest.TestCase):
    def test_loads_latest_close_date_and_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "005930.json").write_text(
                json.dumps({
                    "candles": [
                        {"date": "2026-07-29T00:00:00", "close": 100},
                        {"date": "2026-07-30T00:00:00", "close": 105},
                    ]
                }),
                encoding="utf-8",
            )

            result = _load_latest_prices(root, {"005930", "000660"})

            self.assertEqual("2026-07-30", result["005930"]["date"])
            self.assertEqual(105.0, result["005930"]["close"])
            self.assertAlmostEqual(0.05, result["005930"]["change_rate"])
            self.assertNotIn("000660", result)


if __name__ == "__main__":
    unittest.main()
