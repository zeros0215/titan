"""Immutable, broker-neutral trading domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re


KRW = Decimal("1")
SYMBOL_PATTERN = re.compile(r"^[0-9A-Z]{6}$")


class TradingMode(str, Enum):
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING_SUBMIT = "PENDING_SUBMIT"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _symbol(value: str) -> None:
    if not SYMBOL_PATTERN.fullmatch(value):
        raise ValueError("symbol must be a six-character market code")


@dataclass(frozen=True, slots=True)
class OrderIntent:
    intent_id: str
    strategy_version: str
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    created_at: datetime
    limit_price: Decimal | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.intent_id.strip():
            raise ValueError("intent_id is required")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version is required")
        _symbol(self.symbol)
        _aware(self.created_at, "created_at")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None or self.limit_price <= 0:
                raise ValueError("positive limit_price is required for LIMIT")
        elif self.limit_price is not None:
            raise ValueError("MARKET intent must not contain limit_price")


@dataclass(frozen=True, slots=True)
class MarketQuote:
    symbol: str
    observed_at: datetime
    last_price: Decimal
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None

    def __post_init__(self) -> None:
        _symbol(self.symbol)
        _aware(self.observed_at, "observed_at")
        if self.last_price <= 0:
            raise ValueError("last_price must be positive")
        if self.bid_price is not None and self.bid_price <= 0:
            raise ValueError("bid_price must be positive")
        if self.ask_price is not None and self.ask_price <= 0:
            raise ValueError("ask_price must be positive")


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    quantity: int
    average_price: Decimal
    market_price: Decimal

    def __post_init__(self) -> None:
        _symbol(self.symbol)
        if self.quantity < 0:
            raise ValueError("quantity must not be negative")
        if self.average_price < 0 or self.market_price <= 0:
            raise ValueError("position prices are invalid")

    @property
    def market_value(self) -> Decimal:
        return self.market_price * self.quantity


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    account_ref: str
    observed_at: datetime
    cash: Decimal
    buying_power: Decimal
    positions: tuple[Position, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.account_ref.strip():
            raise ValueError("account_ref is required")
        _aware(self.observed_at, "observed_at")
        if self.cash < 0 or self.buying_power < 0:
            raise ValueError("account balances must not be negative")
        symbols = [position.symbol for position in self.positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("account positions contain duplicate symbols")

    @property
    def gross_market_value(self) -> Decimal:
        return sum(
            (position.market_value for position in self.positions),
            start=Decimal("0"),
        )

    def position(self, symbol: str) -> Position | None:
        return next((item for item in self.positions if item.symbol == symbol), None)


@dataclass(frozen=True, slots=True)
class BrokerOrderRequest:
    intent_id: str
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: Decimal | None


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    broker_order_id: str
    intent_id: str
    symbol: str
    side: OrderSide
    requested_quantity: int
    filled_quantity: int
    status: OrderStatus
    submitted_at: datetime
    limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.broker_order_id or not self.intent_id:
            raise ValueError("order identifiers are required")
        _symbol(self.symbol)
        _aware(self.submitted_at, "submitted_at")
        if self.requested_quantity <= 0:
            raise ValueError("requested_quantity must be positive")
        if not 0 <= self.filled_quantity <= self.requested_quantity:
            raise ValueError("filled_quantity is outside the order quantity")


@dataclass(frozen=True, slots=True)
class Fill:
    broker_order_id: str
    fill_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: Decimal
    fee: Decimal
    filled_at: datetime

    def __post_init__(self) -> None:
        if not self.broker_order_id or not self.fill_id:
            raise ValueError("fill identifiers are required")
        _symbol(self.symbol)
        _aware(self.filled_at, "filled_at")
        if self.quantity <= 0 or self.price <= 0 or self.fee < 0:
            raise ValueError("fill values are invalid")
