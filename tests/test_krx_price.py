import tempfile
import unittest
from datetime import date
from pathlib import Path

from price_history.krx import KrxPriceCollector, KrxPriceRawRepository


class Client:
    def __init__(self):
        self.calls = []

    def fetch(self, market, base_date):
        self.calls.append((market, base_date))
        return {"OutBlock_1": [{"ISU_SRT_CD": "005930"}]}


class KrxPriceTest(unittest.TestCase):
    def test_collection_resumes_from_cached_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = KrxPriceRawRepository(Path(directory))
            client = Client()
            collector = KrxPriceCollector(client, repository)

            first = collector.collect(
                date(2025, 12, 29), date(2025, 12, 30), max_requests=2
            )
            second = collector.collect(
                date(2025, 12, 29), date(2025, 12, 30), max_requests=2
            )

            self.assertFalse(first.completed)
            self.assertTrue(second.completed)
            self.assertEqual(4, len(client.calls))
            self.assertEqual(2, second.skipped_cached)


if __name__ == "__main__":
    unittest.main()
