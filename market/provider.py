"""
Market Provider Interface
"""

from abc import ABC
from abc import abstractmethod

from domain.candle_series import CandleSeries


class MarketProvider(ABC):

    @abstractmethod
    def get_daily_price(
        self,
        code: str
    ) -> CandleSeries:
        """
        Return daily candle series.
        """
        raise NotImplementedError