import unittest

from broker.kis.constants import CURRENT_PRICE_URL, TR_CURRENT_PRICE
from broker.kis.current_price import KisCurrentPriceProvider


class KisCurrentPriceProviderTest(unittest.TestCase):
    def test_reads_current_price_without_order_request(self) -> None:
        session = _Session()
        provider = KisCurrentPriceProvider(session)

        prices = provider.get_prices(["090430"])

        self.assertEqual(CURRENT_PRICE_URL, session.url)
        self.assertEqual(TR_CURRENT_PRICE, session.tr_id)
        self.assertEqual(134000.0, prices["090430"]["close"])
        self.assertAlmostEqual(0.0993, prices["090430"]["change_rate"])
        self.assertEqual("KIS_REALTIME", prices["090430"]["source"])


class _Session:
    def __init__(self) -> None:
        self.client = type("Client", (), {"minimum_interval_seconds": 0.0})()

    def get(self, url, tr_id, params):
        self.url = url
        self.tr_id = tr_id
        self.params = params
        return type("Response", (), {
            "json": lambda self: {
                "rt_cd": "0",
                "output": {
                    "stck_prpr": "134000",
                    "prdy_ctrt": "9.93",
                    "stck_bsop_date": "20260730",
                },
            }
        })()

    def close(self) -> None:
        pass


if __name__ == "__main__":
    unittest.main()
