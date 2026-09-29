"""Deterministic paper broker with explicit failure-injection scenarios."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from trading.model import (
    AccountSnapshot,
    BrokerOrder,
    BrokerOrderRequest,
    Fill,
    OrderSide,
    OrderStatus,
    Position,
)


class SimulatedScenario(str, Enum):
    ACCEPT_ONLY = "ACCEPT_ONLY"
    FULL_FILL = "FULL_FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    REJECT = "REJECT"
    TIMEOUT_AFTER_ACCEPT = "TIMEOUT_AFTER_ACCEPT"
    CANCEL_RACE_FILL = "CANCEL_RACE_FILL"


class SimulatedBrokerTimeout(TimeoutError):
    """The broker may have accepted an order but no response was received."""


@dataclass(frozen=True, slots=True)
class SimulatedBrokerConfig:
    scenario: SimulatedScenario = SimulatedScenario.FULL_FILL
    fill_fee: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.fill_fee < 0:
            raise ValueError("fill_fee must not be negative")


class SimulatedExecutionBroker:
    """In-memory broker used to prove coordinator behavior before any API order."""

    def __init__(
        self,
        account: AccountSnapshot,
        prices: dict[str, Decimal],
        *,
        config: SimulatedBrokerConfig = SimulatedBrokerConfig(),
    ) -> None:
        if any(price <= 0 for price in prices.values()):
            raise ValueError("simulated prices must be positive")
        self._account = account
        self._prices = dict(prices)
        self._config = config
        self._orders: dict[str, BrokerOrder] = {}
        self._intent_orders: dict[str, str] = {}
        self._fills: dict[str, list[Fill]] = {}
        self._next_order = 1
        self._next_fill = 1
        self.submit_count = 0

    def account_snapshot(self) -> AccountSnapshot:
        return self._account

    def open_orders(self) -> tuple[BrokerOrder, ...]:
        active = {
            OrderStatus.PENDING_SUBMIT,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCEL_PENDING,
            OrderStatus.UNKNOWN,
        }
        return tuple(order for order in self._orders.values() if order.status in active)

    def find_order_by_intent(self, intent_id: str) -> BrokerOrder | None:
        order_id = self._intent_orders.get(intent_id)
        return self._orders.get(order_id) if order_id else None

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrder:
        self.submit_count += 1
        if request.intent_id in self._intent_orders:
            raise ValueError("simulator refuses duplicate intent submission")
        order_id = f"sim-order-{self._next_order}"
        self._next_order += 1
        now = datetime.now(timezone.utc)
        status = (
            OrderStatus.REJECTED
            if self._config.scenario is SimulatedScenario.REJECT
            else OrderStatus.ACCEPTED
        )
        order = BrokerOrder(
            order_id,
            request.intent_id,
            request.symbol,
            request.side,
            request.quantity,
            0,
            status,
            now,
            request.limit_price,
        )
        self._orders[order_id] = order
        self._intent_orders[request.intent_id] = order_id
        self._fills[order_id] = []
        if self._config.scenario is SimulatedScenario.FULL_FILL:
            order = self._fill(order, request.quantity)
        elif self._config.scenario is SimulatedScenario.PARTIAL_FILL:
            order = self._fill(order, max(1, request.quantity // 2))
        elif self._config.scenario is SimulatedScenario.TIMEOUT_AFTER_ACCEPT:
            self._orders[order_id] = replace(order, status=OrderStatus.UNKNOWN)
            raise SimulatedBrokerTimeout(
                "simulated timeout after the broker accepted the request"
            )
        return order

    def cancel_order(self, broker_order_id: str) -> BrokerOrder:
        order = self._orders[broker_order_id]
        if self._config.scenario is SimulatedScenario.CANCEL_RACE_FILL:
            return self._fill(
                order, order.requested_quantity - order.filled_quantity
            )
        cancelled = replace(order, status=OrderStatus.CANCELLED)
        self._orders[broker_order_id] = cancelled
        return cancelled

    def fills_for_order(self, broker_order_id: str) -> tuple[Fill, ...]:
        return tuple(self._fills.get(broker_order_id, ()))

    def _fill(self, order: BrokerOrder, quantity: int) -> BrokerOrder:
        if quantity <= 0:
            return order
        price = order.limit_price or self._prices[order.symbol]
        fill = Fill(
            order.broker_order_id,
            f"sim-fill-{self._next_fill}",
            order.symbol,
            order.side,
            quantity,
            price,
            self._config.fill_fee,
            datetime.now(timezone.utc),
        )
        self._next_fill += 1
        self._fills[order.broker_order_id].append(fill)
        filled_quantity = order.filled_quantity + quantity
        status = (
            OrderStatus.FILLED
            if filled_quantity == order.requested_quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        updated = replace(
            order, filled_quantity=filled_quantity, status=status
        )
        self._orders[order.broker_order_id] = updated
        self._apply_fill(fill)
        return updated

    def _apply_fill(self, fill: Fill) -> None:
        positions = {item.symbol: item for item in self._account.positions}
        current = positions.get(fill.symbol)
        cash_delta = fill.price * fill.quantity + fill.fee
        if fill.side is OrderSide.BUY:
            old_quantity = current.quantity if current else 0
            old_cost = (
                current.average_price * old_quantity if current else Decimal("0")
            )
            new_quantity = old_quantity + fill.quantity
            positions[fill.symbol] = Position(
                fill.symbol,
                new_quantity,
                (old_cost + fill.price * fill.quantity) / new_quantity,
                self._prices[fill.symbol],
            )
            cash = self._account.cash - cash_delta
        else:
            if current is None or current.quantity < fill.quantity:
                raise ValueError("simulated sell exceeds the position")
            remaining = current.quantity - fill.quantity
            if remaining:
                positions[fill.symbol] = replace(current, quantity=remaining)
            else:
                positions.pop(fill.symbol)
            cash = self._account.cash + fill.price * fill.quantity - fill.fee
        self._account = AccountSnapshot(
            self._account.account_ref,
            fill.filled_at,
            cash,
            cash,
            tuple(sorted(positions.values(), key=lambda item: item.symbol)),
        )
