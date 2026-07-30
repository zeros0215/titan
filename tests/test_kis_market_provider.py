import unittest
from datetime import datetime

from broker.kis.constants import DAILY_ITEM_CHART_PRICE_URL, TR_DAILY_ITEM_CHART_PRICE
from broker.kis.market import KisMarketProvider
from domain.enums import MarketType
from domain.stock import Stock


class KisMarketProviderTest(unittest.TestCase):
    def test_requests_chart_prices_with_a_date_range(self) -> None:
        client = _Client()
        provider = object.__new__(KisMarketProvider)
        provider.session = _Session(client)

        series = provider.get_daily_price(Stock("005930", "Samsung", MarketType.KOSPI), count=100)

        self.assertEqual(series.latest.close, 70_000.0)
        self.assertEqual(client.url, DAILY_ITEM_CHART_PRICE_URL)
        self.assertEqual(client.headers["tr_id"], TR_DAILY_ITEM_CHART_PRICE)
        self.assertIn("FID_INPUT_DATE_1", client.params)
        self.assertIn("FID_INPUT_DATE_2", client.params)

    def test_uses_the_explicit_point_in_time_date_range(self) -> None:
        client = _Client()
        provider = object.__new__(KisMarketProvider)
        provider.session = _Session(client)

        provider.get_daily_prices(
            Stock("005930", "Samsung", MarketType.KOSPI),
            datetime(2025, 1, 2),
            datetime(2025, 6, 30),
        )

        self.assertEqual(client.params["FID_INPUT_DATE_1"], "20250102")
        self.assertEqual(client.params["FID_INPUT_DATE_2"], "20250630")


class _Session:
    def __init__(self, client) -> None:
        self.auth = _Auth()
        self.client = client


class _Auth:
    def get_token(self):
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
            "output2": [{
                "stck_bsop_date": "20260727",
                "stck_oprc": "70000",
                "stck_hgpr": "71000",
                "stck_lwpr": "69000",
                "stck_clpr": "70000",
                "acml_vol": "1000000",
            }],
        }


if __name__ == "__main__":
    unittest.main()
