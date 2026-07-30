"""Canonical market-data provider contract used by the V1 pipeline."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from domain.candle_series import CandleSeries
from domain.stock import Stock


class MarketProvider(ABC):
    @abstractmethod
    def get_daily_prices(
        self,
        stock: Stock,
        start_date: datetime,
        end_date: datetime,
    ) -> CandleSeries:
        """Return daily candles in the inclusive point-in-time date range."""
        raise NotImplementedError

    def get_daily_price(
        self,
        stock: Stock,
        count: int = 100,
    ) -> CandleSeries:
        """Backward-compatible count-based access for external V1 callers."""
        if count <= 0:
            raise ValueError("count must be greater than zero")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=count + 30)
        series = self.get_daily_prices(stock, start_date, end_date)
        return CandleSeries(stock, series.candles[-count:])


def load_daily_prices(
    provider,
    stock: Stock,
    start_date: datetime,
    end_date: datetime,
) -> CandleSeries:
    """Use the canonical contract, with temporary support for legacy test doubles."""
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    method = getattr(provider, "get_daily_prices", None)
    if method is not None:
        return method(stock, start_date, end_date)

    # Remove this compatibility path after all downstream providers migrate.
    series = provider.get_daily_price(stock)
    return CandleSeries(
        stock=series.stock,
        candles=[
            candle
            for candle in series.candles
            if start_date <= candle.date <= end_date
        ],
    )
