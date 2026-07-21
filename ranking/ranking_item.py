"""
Ranking Item
"""

from dataclasses import dataclass

from domain.stock import Stock

from features.feature import Feature

from factors.factor_score import FactorScore

from strategy.strategy_result import StrategyResult

from backtest.result import BacktestResult


@dataclass(slots=True)
class RankingItem:

    stock: Stock

    feature: Feature

    factor: FactorScore

    strategy: StrategyResult

    result: BacktestResult | None = None