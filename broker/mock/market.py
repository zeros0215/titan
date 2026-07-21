"""
Mock Market Provider
"""

from broker.provider import MarketProvider

from broker.mock.generator import MockGenerator

from domain.stock import Stock
from domain.candle_series import CandleSeries


class MockMarketProvider(MarketProvider):

    def __init__(
        self,
        scenario=None
    ):
        self.scenario = scenario

    def get_daily_price(
        self,
        stock: Stock,
        count: int = 100
    ) -> CandleSeries:

        return MockGenerator.create(
            stock,
            count
        )