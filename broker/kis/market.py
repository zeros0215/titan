"""
KIS Market Provider
"""

from broker.kis.header import HeaderBuilder
from broker.provider import MarketProvider

from broker.kis.request.daily_price_request import DailyPriceRequest

from broker.kis.constants import (
    DAILY_PRICE_URL,
    TR_DAILY_PRICE,
)

from broker.kis.session import KisSession

from broker.kis.dto.market_response import DailyPriceResponse

from broker.kis.mapper.market_mapper import MarketMapper

from domain.stock import Stock
from domain.candle_series import CandleSeries


class KisMarketProvider(MarketProvider):

    def __init__(self):

        self.session = KisSession()


    def get_daily_price(
        self,
        stock: Stock,
        count: int = 100
    ) -> CandleSeries:
        """
        일봉 데이터 조회

        KIS API
            ↓
        DailyPriceResponse
            ↓
        CandleSeries
        """

        token = self.session.auth.get_token()

        headers = HeaderBuilder.authorization(
            token,
            TR_DAILY_PRICE
        )

        request = DailyPriceRequest(
            stock.code
        )

        response = self.session.client.get(
            DAILY_PRICE_URL,
            headers=headers,
            params=request.to_params()
        )

        dto = DailyPriceResponse.from_json(
            response.json()
        )

        return MarketMapper.to_candle_series(
            stock,
            dto
        )