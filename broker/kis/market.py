"""
KIS Market Provider
"""

from broker.kis.header import HeaderBuilder
from broker.provider import MarketProvider
from broker.kis.constants import (
    DAILY_ITEM_CHART_PRICE_URL,
    TR_DAILY_ITEM_CHART_PRICE,
)
from datetime import datetime, timedelta

from broker.kis.session import KisSession

from broker.kis.dto.market_response import (
    DailyPriceResponse,
)

from broker.kis.mapper.market_mapper import (
    MarketMapper,
)

from domain.stock import Stock


class KisMarketProvider(

    MarketProvider

):

    def __init__(self, session: KisSession | None = None):

        self.session = session or KisSession()

    def get_daily_price(

        self,

        stock: Stock,

        count: int = 100

    ):

        # headers = (

        #     self.session.authorization_header()

        # )
        
        # headers = HeaderBuilder.json()

        # headers["appkey"] = self.session.auth.client.client.base_url  # ← 다음 Sprint에서 개선
        # headers["appsecret"] = ""                                    # ← 다음 Sprint에서 개선
        # headers["tr_id"] = TR_DAILY_PRICE

        if count <= 0:
            raise ValueError("count must be greater than zero")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=count + 30)
        series = self.get_daily_prices(stock, start_date, end_date)
        return type(series)(stock, series.candles[-count:])

    def get_daily_prices(
        self,
        stock: Stock,
        start_date: datetime,
        end_date: datetime,
    ):
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        token = self.session.auth.get_token()

        headers = HeaderBuilder.authorization(

            token,

            TR_DAILY_ITEM_CHART_PRICE

        )

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock.code,
            "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "1",
        }

        response = self.session.client.get(

            DAILY_ITEM_CHART_PRICE_URL,

            headers=headers,

            params=params

        )

        dto = DailyPriceResponse.from_json(

            response.json()

        )

        return MarketMapper.to_candle_series(

            stock,

            dto

        )
