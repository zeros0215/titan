"""Broker-neutral, fail-closed pre-trade risk checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from trading.model import (
    AccountSnapshot,
    BrokerOrderRequest,
    MarketQuote,
    OrderIntent,
    OrderSide,
    OrderStatus,
    TradingMode,
    BrokerOrder,
)
from trading.reconciliation import ReconciliationResult
from trading.market_rules import (
    MarketRuleReason,
    MarketRulesSnapshot,
    validate_market_order,
)


class RiskReason(str, Enum):
    APPROVED = "APPROVED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    LIVE_TRADING_DISABLED = "LIVE_TRADING_DISABLED"
    ACCOUNT_NOT_RECONCILED = "ACCOUNT_NOT_RECONCILED"
    ACCOUNT_SNAPSHOT_STALE = "ACCOUNT_SNAPSHOT_STALE"
    ORDER_INTENT_STALE = "ORDER_INTENT_STALE"
    QUOTE_MISSING_OR_STALE = "QUOTE_MISSING_OR_STALE"
    DUPLICATE_INTENT = "DUPLICATE_INTENT"
    SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    TOO_MANY_OPEN_ORDERS = "TOO_MANY_OPEN_ORDERS"
    ORDER_VALUE_LIMIT = "ORDER_VALUE_LIMIT"
    POSITION_VALUE_LIMIT = "POSITION_VALUE_LIMIT"
    GROSS_EXPOSURE_LIMIT = "GROSS_EXPOSURE_LIMIT"
    INSUFFICIENT_BUYING_POWER = "INSUFFICIENT_BUYING_POWER"
    INSUFFICIENT_POSITION = "INSUFFICIENT_POSITION"
    MARKET_RULES_MISSING = "MARKET_RULES_MISSING"
    MARKET_RULES_STALE = "MARKET_RULES_STALE"
    MARKET_RULE_SYMBOL_MISMATCH = "MARKET_RULE_SYMBOL_MISMATCH"
    VENUE_NOT_KRX = "VENUE_NOT_KRX"
    SESSION_NOT_REGULAR = "SESSION_NOT_REGULAR"
    LIMIT_PRICE_OFF_TICK = "LIMIT_PRICE_OFF_TICK"
    LIMIT_PRICE_OUTSIDE_DAILY_RANGE = "LIMIT_PRICE_OUTSIDE_DAILY_RANGE"


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_order_value: Decimal
    max_position_value: Decimal
    max_gross_exposure: Decimal
    max_daily_loss: Decimal
    max_open_orders: int = 5
    max_quote_age: timedelta = timedelta(seconds=5)
    max_account_age: timedelta = timedelta(seconds=30)
    max_intent_age: timedelta = timedelta(seconds=30)
    allowed_symbols: frozenset[str] = field(default_factory=frozenset)
    require_market_rules: bool = False
    max_market_rules_age: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        money = (
            self.max_order_value,
            self.max_position_value,
            self.max_gross_exposure,
            self.max_daily_loss,
        )
        if any(value <= 0 for value in money):
            raise ValueError("risk money limits must be positive")
        if self.max_open_orders <= 0:
            raise ValueError("max_open_orders must be positive")
        if self.max_quote_age <= timedelta(0):
            raise ValueError("max_quote_age must be positive")
        if self.max_account_age <= timedelta(0):
            raise ValueError("max_account_age must be positive")
        if self.max_intent_age <= timedelta(0):
            raise ValueError("max_intent_age must be positive")
        if self.max_market_rules_age <= timedelta(0):
            raise ValueError("max_market_rules_age must be positive")


@dataclass(frozen=True, slots=True)
class RiskContext:
    mode: TradingMode
    now: datetime
    account: AccountSnapshot
    reconciliation: ReconciliationResult
    quote: MarketQuote | None
    open_orders: tuple[BrokerOrder, ...] = field(default_factory=tuple)
    seen_intent_ids: frozenset[str] = field(default_factory=frozenset)
    realized_pnl_today: Decimal = Decimal("0")
    reserved_buying_power: Decimal = Decimal("0")
    kill_switch_active: bool = False
    live_orders_enabled: bool = False
    market_rules: MarketRulesSnapshot | None = None

    def __post_init__(self) -> None:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if self.reserved_buying_power < 0:
            raise ValueError("reserved_buying_power must not be negative")


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reasons: tuple[RiskReason, ...]
    estimated_price: Decimal | None = None
    estimated_order_value: Decimal | None = None
    request: BrokerOrderRequest | None = None


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskDecision:
        reasons: list[RiskReason] = []
        if context.kill_switch_active:
            reasons.append(RiskReason.KILL_SWITCH_ACTIVE)
        if context.mode is TradingMode.LIVE and not context.live_orders_enabled:
            reasons.append(RiskReason.LIVE_TRADING_DISABLED)
        if not context.reconciliation.ready:
            reasons.append(RiskReason.ACCOUNT_NOT_RECONCILED)
        account_age = context.now - context.account.observed_at
        if account_age < timedelta(0) or account_age > self.limits.max_account_age:
            reasons.append(RiskReason.ACCOUNT_SNAPSHOT_STALE)
        intent_age = context.now - intent.created_at
        if intent_age < timedelta(0) or intent_age > self.limits.max_intent_age:
            reasons.append(RiskReason.ORDER_INTENT_STALE)
        quote = context.quote
        if (
            quote is None
            or quote.symbol != intent.symbol
            or context.now - quote.observed_at > self.limits.max_quote_age
            or quote.observed_at > context.now
        ):
            reasons.append(RiskReason.QUOTE_MISSING_OR_STALE)
        if intent.intent_id in context.seen_intent_ids:
            reasons.append(RiskReason.DUPLICATE_INTENT)
        if self.limits.require_market_rules:
            if context.market_rules is None:
                reasons.append(RiskReason.MARKET_RULES_MISSING)
            else:
                market_decision = validate_market_order(
                    intent,
                    context.market_rules,
                    now=context.now,
                    maximum_age_seconds=int(
                        self.limits.max_market_rules_age.total_seconds()
                    ),
                )
                reasons.extend(
                    RiskReason(reason.value)
                    for reason in market_decision.reasons
                    if reason is not MarketRuleReason.APPROVED
                )
        if (
            self.limits.allowed_symbols
            and intent.symbol not in self.limits.allowed_symbols
        ):
            reasons.append(RiskReason.SYMBOL_NOT_ALLOWED)
        if context.realized_pnl_today <= -self.limits.max_daily_loss:
            reasons.append(RiskReason.DAILY_LOSS_LIMIT)
        active_orders = tuple(
            order for order in context.open_orders
            if order.status in {
                OrderStatus.PENDING_SUBMIT,
                OrderStatus.ACCEPTED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.CANCEL_PENDING,
                OrderStatus.UNKNOWN,
            }
        )
        if len(active_orders) >= self.limits.max_open_orders:
            reasons.append(RiskReason.TOO_MANY_OPEN_ORDERS)

        estimated_price = self._estimated_price(intent, quote)
        if estimated_price is None:
            return RiskDecision(False, tuple(dict.fromkeys(reasons)), None, None)
        order_value = estimated_price * intent.quantity
        if order_value > self.limits.max_order_value:
            reasons.append(RiskReason.ORDER_VALUE_LIMIT)

        position = context.account.position(intent.symbol)
        held_quantity = position.quantity if position else 0
        pending_buy = sum(
            order.requested_quantity - order.filled_quantity
            for order in active_orders
            if order.symbol == intent.symbol and order.side is OrderSide.BUY
        )
        pending_sell = sum(
            order.requested_quantity - order.filled_quantity
            for order in active_orders
            if order.symbol == intent.symbol and order.side is OrderSide.SELL
        )
        if intent.side is OrderSide.BUY:
            projected_quantity = held_quantity + pending_buy + intent.quantity
            projected_value = estimated_price * projected_quantity
            if projected_value > self.limits.max_position_value:
                reasons.append(RiskReason.POSITION_VALUE_LIMIT)
            projected_gross = context.account.gross_market_value + order_value
            if projected_gross > self.limits.max_gross_exposure:
                reasons.append(RiskReason.GROSS_EXPOSURE_LIMIT)
            reserved = context.reserved_buying_power + sum(
                self._remaining_value(order)
                for order in active_orders if order.side is OrderSide.BUY
            )
            if order_value + reserved > context.account.buying_power:
                reasons.append(RiskReason.INSUFFICIENT_BUYING_POWER)
        elif intent.quantity + pending_sell > held_quantity:
            reasons.append(RiskReason.INSUFFICIENT_POSITION)

        unique_reasons = tuple(dict.fromkeys(reasons))
        if unique_reasons:
            return RiskDecision(False, unique_reasons, estimated_price, order_value)
        request = BrokerOrderRequest(
            intent.intent_id,
            intent.symbol,
            intent.side,
            intent.quantity,
            intent.order_type,
            intent.limit_price,
        )
        return RiskDecision(
            True,
            (RiskReason.APPROVED,),
            estimated_price,
            order_value,
            request,
        )

    @staticmethod
    def _estimated_price(
        intent: OrderIntent, quote: MarketQuote | None
    ) -> Decimal | None:
        if intent.limit_price is not None:
            return intent.limit_price
        if quote is None:
            return None
        if intent.side is OrderSide.BUY:
            return quote.ask_price or quote.last_price
        return quote.bid_price or quote.last_price

    def _remaining_value(self, order: BrokerOrder) -> Decimal:
        remaining = order.requested_quantity - order.filled_quantity
        if order.limit_price is None:
            return self.limits.max_order_value
        return order.limit_price * remaining
