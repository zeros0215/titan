"""Interfaces implemented by a future broker adapter and durable ledger."""

from __future__ import annotations

from typing import Protocol

from trading.model import AccountSnapshot, BrokerOrder, BrokerOrderRequest


class ExecutionBroker(Protocol):
    """Broker boundary. No implementation is provided in this repository yet."""

    def account_snapshot(self) -> AccountSnapshot: ...

    def open_orders(self) -> tuple[BrokerOrder, ...]: ...

    def find_order_by_intent(self, intent_id: str) -> BrokerOrder | None: ...

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrder: ...

    def cancel_order(self, broker_order_id: str) -> BrokerOrder: ...


class ExecutionJournal(Protocol):
    """Append-only persistence required before a future order submission."""

    def has_intent(self, intent_id: str) -> bool: ...

    def record_intent(self, payload: dict) -> None: ...

    def record_risk_decision(self, payload: dict) -> None: ...

    def record_broker_order(self, payload: dict) -> None: ...
