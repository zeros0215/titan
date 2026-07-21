from dataclasses import dataclass

from domain.stock import Stock
from backtest.result import BacktestResult


@dataclass(slots=True)
class RankingItem:

    stock: Stock

    score: int

    signal: str

    result: BacktestResult | None = None