"""
Market Provider
"""

from abc import ABC

from abc import abstractmethod


class MarketProvider(ABC):

    @abstractmethod
    def get_market_series(self):

        pass