"""
KIS Market API
"""

from datetime import datetime
from datetime import timedelta

from broker.kis.constants import (
    DAILY_PRICE_URL,
    TR_ID_DAILY_PRICE,
    MARKET_DIVISION,
    PERIOD_DAY,
    ORIGINAL_PRICE,
)


class KisMarketApi:

    def __init__(self, session):

        self.session = session

    def get_daily_price(
        self,
        code: str,
        days: int = 120,
    ):

        today = datetime.today()

        start = today - timedelta(days=days)

        # headers = {
        #     "tr_id": TR_ID_DAILY_PRICE
        # }

        params = {
            "FID_COND_MRKT_DIV_CODE": MARKET_DIVISION,
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": today.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": PERIOD_DAY,
            "FID_ORG_ADJ_PRC": ORIGINAL_PRICE,
        }

        # response = self.session.get(
        #     DAILY_PRICE_URL,
        #     headers=headers,
        #     params=params,
        # )

        response = self.session.get(
            url=DAILY_PRICE_URL,
            tr_id=TR_ID_DAILY_PRICE,
            params=params
        )

        return response.json()