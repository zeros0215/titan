from datetime import datetime
import unittest

from benchmark.kis import KisBenchmarkProvider
from benchmark.mock import MockBenchmarkProvider
from broker.kis.constants import (
    DAILY_INDEX_CHART_PRICE_URL,
    TR_DAILY_INDEX_CHART_PRICE,
)
from domain.enums import MarketType


class MockBenchmarkProviderTest(unittest.TestCase):
    def test_returns_deterministic_market_returns(self) -> None:
        provider = MockBenchmarkProvider()
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 11)

        first = provider.get_returns({MarketType.KOSPI}, start, end)
        second = provider.get_returns({MarketType.KOSPI}, start, end)

        self.assertEqual(first, second)
        self.assertGreater(first["KOSPI"], 0)


class KisBenchmarkProviderTest(unittest.TestCase):
    def test_requests_and_calculates_kospi_period_return(self) -> None:
        client = _Client()
        provider = KisBenchmarkProvider(_Session(client))

        returns = provider.get_returns(
            {MarketType.KOSPI},
            datetime(2026, 1, 2),
            datetime(2026, 1, 20),
        )

        self.assertAlmostEqual(returns["KOSPI"], 0.10)
        self.assertEqual(client.url, DAILY_INDEX_CHART_PRICE_URL)
        self.assertEqual(client.headers["tr_id"], TR_DAILY_INDEX_CHART_PRICE)
        self.assertEqual(client.params["FID_COND_MRKT_DIV_CODE"], "U")
        self.assertEqual(client.params["FID_INPUT_ISCD"], "0001")
        self.assertEqual(client.params["FID_INPUT_DATE_1"], "20260102")
        self.assertEqual(client.params["FID_INPUT_DATE_2"], "20260120")


class _Session:
    def __init__(self, client) -> None:
        self.auth = _Auth()
        self.client = client


class _Auth:
    @staticmethod
    def get_token():
        return type("Token", (), {"access_token": "test-token"})()


class _Client:
    def get(self, url, headers, params):
        self.url = url
        self.headers = headers
        self.params = params
        return _Response()


class _Response:
    @staticmethod
    def json():
        return {
            "rt_cd": "0",
            "output2": [
                {"stck_bsop_date": "20260120", "bstp_nmix_prpr": "110.0"},
                {"stck_bsop_date": "20260102", "bstp_nmix_prpr": "100.0"},
            ],
        }


if __name__ == "__main__":
    unittest.main()
