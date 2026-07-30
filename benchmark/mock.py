from datetime import datetime

from benchmark.provider import BenchmarkProvider
from domain.enums import MarketType


class MockBenchmarkProvider(BenchmarkProvider):
    """Deterministic local benchmark used by MOCK validation."""

    DAILY_RETURNS = {
        MarketType.KOSPI: 0.0003,
        MarketType.KOSDAQ: 0.0004,
    }

    def get_returns(
        self,
        markets: set[MarketType],
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, float]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        days = (end_date.date() - start_date.date()).days
        return {
            market.value: (1 + self.DAILY_RETURNS[market]) ** days - 1
            for market in markets
        }
