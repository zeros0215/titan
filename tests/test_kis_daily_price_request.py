import unittest

from broker.kis.constants import DAILY_PRICE_URL, TR_DAILY_PRICE
from broker.kis.request.daily_price_request import DailyPriceRequest


class KisDailyPriceRequestTest(unittest.TestCase):
    def test_uses_the_daily_price_endpoint_and_its_matching_tr_id(self) -> None:
        request = DailyPriceRequest("005930")

        self.assertEqual(
            DAILY_PRICE_URL,
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
        )
        self.assertEqual(TR_DAILY_PRICE, "FHKST01010400")
        self.assertEqual(request.to_params()["FID_INPUT_ISCD"], "005930")
        self.assertNotIn("FID_INPUT_DATE_1", request.to_params())


if __name__ == "__main__":
    unittest.main()
