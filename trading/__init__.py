"""Broker-neutral live-trading boundaries.

This package deliberately contains no brokerage implementation. Strategies may
create order intents, but only a separately wired execution adapter can submit
an approved request.
"""

from trading.model import (
    AccountSnapshot,
    BrokerOrder,
    BrokerOrderRequest,
    Fill,
    MarketQuote,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradingMode,
)
from trading.reconciliation import (
    InternalPortfolioSnapshot,
    ReconciliationResult,
    reconcile_account,
)
from trading.risk import (
    RiskContext,
    RiskDecision,
    RiskLimits,
    RiskManager,
)

__all__ = [
    "AccountSnapshot",
    "BrokerOrder",
    "BrokerOrderRequest",
    "Fill",
    "InternalPortfolioSnapshot",
    "MarketQuote",
    "OrderIntent",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "ReconciliationResult",
    "RiskContext",
    "RiskDecision",
    "RiskLimits",
    "RiskManager",
    "TradingMode",
    "reconcile_account",
]
