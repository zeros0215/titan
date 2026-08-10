import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from benchmark.equal_weight import HistoricalEqualWeightBenchmarkProvider
from domain.enums import MarketType


class EqualWeightBenchmarkTest(unittest.TestCase):
    def test_calculates_point_in_time_equal_weight_return(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "market_cap_top500.json").write_text(json.dumps({
                "sessions": {"2026-01-02T00:00:00": ["1", "2"]}
            }), encoding="utf-8")
            for code, last in (("000001", 110), ("000002", 120)):
                (root / f"{code}.json").write_text(json.dumps({"candles": [
                    {"date": "2026-01-02T00:00:00", "close": 100},
                    {"date": "2026-01-05T00:00:00", "close": last},
                ]}), encoding="utf-8")

            result = HistoricalEqualWeightBenchmarkProvider(root).get_returns(
                {MarketType.KOSPI},
                datetime(2026, 1, 2), datetime(2026, 1, 5),
            )

            self.assertAlmostEqual(0.15, result["KOSPI"])


if __name__ == "__main__":
    unittest.main()
