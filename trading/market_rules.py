"""Broker-neutral KRX order constraints used before broker submission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from trading.model import OrderIntent, OrderType


class MarketRuleReason(str, Enum):
    APPROVED = "APPROVED"
    RULES_MISSING = "MARKET_RULES_MISSING"
    RULES_STALE = "MARKET_RULES_STALE"
    SYMBOL_MISMATCH = "MARKET_RULE_SYMBOL_MISMATCH"
    VENUE_NOT_KRX = "VENUE_NOT_KRX"
    SESSION_NOT_REGULAR = "SESSION_NOT_REGULAR"
    LIMIT_PRICE_OFF_TICK = "LIMIT_PRICE_OFF_TICK"
    LIMIT_PRICE_OUTSIDE_DAILY_RANGE = "LIMIT_PRICE_OUTSIDE_DAILY_RANGE"


@dataclass(frozen=True, slots=True)
class MarketRulesSnapshot:
    symbol: str
    venue: str
    observed_at: datetime
    regular_session_open: bool
    reference_price: Decimal
    lower_limit_price: Decimal
    upper_limit_price: Decimal
    tick_size: Decimal

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("market rules observed_at must be timezone-aware")
        if self.venue != "KRX":
            raise ValueError("paper market rules only support KRX")
        if len(self.symbol) != 6 or not self.symbol.isdigit():
            raise ValueError("market rule symbol must be a six-digit KRX code")
        prices = (
            self.reference_price,
            self.lower_limit_price,
            self.upper_limit_price,
            self.tick_size,
        )
        if any(value <= 0 for value in prices):
            raise ValueError("market rule prices must be positive")
        if not self.lower_limit_price <= self.reference_price <= self.upper_limit_price:
            raise ValueError("reference price must be inside the daily range")
        tolerance = self.tick_size
        if self.lower_limit_price < self.reference_price * Decimal("0.70") - tolerance:
            raise ValueError("lower limit exceeds the KRX 30 percent boundary")
        if self.upper_limit_price > self.reference_price * Decimal("1.30") + tolerance:
            raise ValueError("upper limit exceeds the KRX 30 percent boundary")


@dataclass(frozen=True, slots=True)
class MarketRuleDecision:
    approved: bool
    reasons: tuple[MarketRuleReason, ...]


def validate_market_order(
    intent: OrderIntent,
    rules: MarketRulesSnapshot,
    *,
    now: datetime,
    maximum_age_seconds: int,
) -> MarketRuleDecision:
    reasons: list[MarketRuleReason] = []
    age_seconds = (now - rules.observed_at).total_seconds()
    if age_seconds < 0 or age_seconds > maximum_age_seconds:
        reasons.append(MarketRuleReason.RULES_STALE)
    if rules.symbol != intent.symbol:
        reasons.append(MarketRuleReason.SYMBOL_MISMATCH)
    if rules.venue != "KRX":
        reasons.append(MarketRuleReason.VENUE_NOT_KRX)
    if not rules.regular_session_open:
        reasons.append(MarketRuleReason.SESSION_NOT_REGULAR)
    if intent.order_type is OrderType.LIMIT:
        price = intent.limit_price
        if price is None or price % rules.tick_size:
            reasons.append(MarketRuleReason.LIMIT_PRICE_OFF_TICK)
        elif not rules.lower_limit_price <= price <= rules.upper_limit_price:
            reasons.append(MarketRuleReason.LIMIT_PRICE_OUTSIDE_DAILY_RANGE)
    unique = tuple(dict.fromkeys(reasons))
    return MarketRuleDecision(
        not unique,
        unique or (MarketRuleReason.APPROVED,),
    )
