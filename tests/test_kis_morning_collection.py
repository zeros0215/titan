import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.collect_kis_morning_bars import _five_minute_bars


class KisMorningCollectionTest(unittest.TestCase):
    def test_aggregates_one_minute_rows_to_twelve_five_minute_bars(self):
        rows = []
        for minute in range(60):
            rows.append({
                "date": "20260105",
                "time": f"09{minute:02d}00",
                "open": 100 + minute,
                "high": 101 + minute,
                "low": 99 + minute,
                "close": 100.5 + minute,
                "volume": 10,
                "trading_value": None,
            })
        bars = _five_minute_bars(rows, "005930")
        self.assertEqual(12, len(bars))
        self.assertEqual(100, bars[0]["open"])
        self.assertEqual(104.5, bars[0]["close"])
        self.assertEqual(50, bars[0]["volume"])


if __name__ == "__main__":
    unittest.main()
