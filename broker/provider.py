"""
Market Provider Interface
"""

from abc import ABC
from abc import abstractmethod

from domain.candle_series import CandleSeries
from domain.stock import Stock


class MarketProvider(ABC):

    @abstractmethod
    def get_daily_price(
        self,
        stock: Stock,
        count: int = 100
    ) -> CandleSeries:
        """
        종목의 일봉 데이터를 조회한다.

        Returns
        -------
        CandleSeries
        """
        raise NotImplementedError