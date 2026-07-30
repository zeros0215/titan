"""Deterministic OHLCV generator for local V1 verification."""

from datetime import datetime, timedelta
import random

from broker.mock.scenario import MarketScenario
from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.stock import Stock


class MockGenerator:
    @staticmethod
    def create(
        stock: Stock,
        count: int = 100,
        reference_date: datetime | None = None,
        scenario: MarketScenario = MarketScenario.BULL,
    ) -> CandleSeries:
        if count <= 0:
            raise ValueError("count must be greater than zero")

        reference = (reference_date or datetime.now()).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        randomizer = random.Random(MockGenerator._seed(stock, reference, scenario))
        base_price = 50_000 + randomizer.randint(0, 40_000)
        candles = []
        for index in range(count):
            drift = MockGenerator._drift(scenario, index, count)
            change = drift + randomizer.uniform(-0.012, 0.012)
            open_price = base_price
            close_price = base_price * (1 + change)
            high_price = max(open_price, close_price) * (1 + randomizer.uniform(0.002, 0.01))
            low_price = min(open_price, close_price) * (1 - randomizer.uniform(0.002, 0.01))
            volume_multiplier = 2 if scenario is MarketScenario.BREAKOUT and index >= count - 20 else 1
            candles.append(Candle(
                date=reference - timedelta(days=count - index),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=randomizer.randint(1_000_000, 5_000_000) * volume_multiplier,
            ))
            base_price = close_price

        return CandleSeries(stock=stock, candles=candles)

    @staticmethod
    def _seed(stock: Stock, reference: datetime, scenario: MarketScenario) -> str:
        return f"{stock.code}:{reference:%Y%m%d}:{scenario.value}"

    @staticmethod
    def _drift(scenario: MarketScenario, index: int, count: int) -> float:
        if scenario is MarketScenario.BEAR:
            return -0.002
        if scenario is MarketScenario.BREAKOUT:
            return 0.001 if index < count - 20 else 0.008
        if scenario is MarketScenario.CRASH:
            return 0.0 if index < count - 20 else -0.008
        if scenario is MarketScenario.SIDEWAYS:
            return 0.0
        return 0.002
