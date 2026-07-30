from abc import ABC, abstractmethod
from datetime import datetime

from domain.enums import MarketType


class BenchmarkProvider(ABC):
    @abstractmethod
    def get_returns(
        self,
        markets: set[MarketType],
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, float]:
        """Return market-keyed benchmark returns for the requested period."""
        raise NotImplementedError
