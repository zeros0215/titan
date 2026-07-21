"""
KIS Daily Price Request
"""

from dataclasses import dataclass
from broker.kis.constants import (

    MARKET_KOSPI,

    PERIOD_DAY,

    ADJUSTED_PRICE,

)

@dataclass(slots=True, frozen=True)
class DailyPriceRequest:

    stock_code: str

    market_code: str = MARKET_KOSPI

    period_code: str = PERIOD_DAY

    adjusted_price: str = ADJUSTED_PRICE

    def to_params(self) -> dict:

        return {

            "FID_COND_MRKT_DIV_CODE": self.market_code,

            "FID_INPUT_ISCD": self.stock_code,

            "FID_PERIOD_DIV_CODE": self.period_code,

            "FID_ORG_ADJ_PRC": self.adjusted_price,

        }