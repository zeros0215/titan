import unittest
from datetime import date

from broker.kis.constants import (
    TIME_DAILY_CHART_PRICE_URL,
    TR_TIME_DAILY_CHART_PRICE,
)
from broker.kis.intraday import KisIntradayProvider


class KisIntradayProviderTest(unittest.TestCase):
    def test_requests_historical_minutes_read_only(self):
        client = _Client()
        provider = KisIntradayProvider(_Session(client))
        rows = provider.get_minutes("005930", date(2026, 1, 5))
        self.assertEqual(TIME_DAILY_CHART_PRICE_URL, client.url)
        self.assertEqual(TR_TIME_DAILY_CHART_PRICE, client.headers["tr_id"])
        self.assertEqual("20260105", client.params["FID_INPUT_DATE_1"])
        self.assertEqual("100000", client.params["FID_INPUT_HOUR_1"])
        self.assertEqual("090000", rows[0]["time"])


class _Session:
    def __init__(self, client):
        self.client = client
        self.auth = type("Auth", (), {
            "get_token": lambda self: type(
                "Token", (), {"access_token": "token"}
            )()
        })()


class _Client:
    def get(self, url, headers, params):
        self.url = url
        self.headers = headers
        self.params = params
        return type("Response", (), {
            "json": lambda self: {
                "rt_cd": "0",
                "output2": [{
                    "stck_bsop_date": "20260105",
                    "stck_cntg_hour": "090000",
                    "stck_oprc": "100",
                    "stck_hgpr": "101",
                    "stck_lwpr": "99",
                    "stck_prpr": "100",
                    "cntg_vol": "10",
                }],
            }
        })()


if __name__ == "__main__":
    unittest.main()
