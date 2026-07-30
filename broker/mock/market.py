"""Deterministic market-data provider for local V1 verification."""

from datetime import datetime, timedelta

from broker.mock.generator import MockGenerator
from broker.mock.scenario import MarketScenario
from broker.provider import MarketProvider
from domain.candle_series import CandleSeries
from domain.stock import Stock


class MockMarketProvider(MarketProvider):
    def __init__(
        self,
        scenario: MarketScenario = MarketScenario.BULL,
        reference_date: datetime | None = None,
    ) -> None:
        self.scenario = scenario
        self.reference_date = reference_date

    def get_daily_price(self, stock: Stock, count: int = 100) -> CandleSeries:
        return MockGenerator.create(
            stock=stock,
            count=count,
            reference_date=self.reference_date,
            scenario=self.scenario,
        )

    def get_daily_prices(
        self,
        stock: Stock,
        start_date: datetime,
        end_date: datetime,
    ) -> CandleSeries:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        count = (end_date.date() - start_date.date()).days + 1
        series = MockGenerator.create(
            stock=stock,
            count=count,
            reference_date=end_date + timedelta(days=1),
            scenario=self.scenario,
        )
        return CandleSeries(
            stock=stock,
            candles=[
                candle
                for candle in series.candles
                if start_date.date() <= candle.date.date() <= end_date.date()
            ],
        )
