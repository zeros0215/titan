from abc import ABC
from abc import abstractmethod

from domain.candle_series import CandleSeries


class MarketDataProvider(ABC):

    @abstractmethod
    def get_daily_price(
        self,
        code: str,
        days: int = 365
    ) -> CandleSeries:
        pass