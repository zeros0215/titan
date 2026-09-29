"""Interfaces implemented by a future broker adapter and durable ledger."""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

from trading.model import AccountSnapshot, BrokerOrder, BrokerOrderRequest

if TYPE_CHECKING:
    from trading.journal import IntegrityResult, JournalEvent, JournalRecord


class ExecutionBroker(Protocol):
    """Broker boundary. No implementation is provided in this repository yet."""

    def account_snapshot(self) -> AccountSnapshot: ...

    def open_orders(self) -> tuple[BrokerOrder, ...]: ...

    def find_order_by_intent(self, intent_id: str) -> BrokerOrder | None: ...

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrder: ...

    def cancel_order(self, broker_order_id: str) -> BrokerOrder: ...


class ExecutionJournal(Protocol):
    """Append-only persistence required before a future order submission."""

    def append(self, event: "JournalEvent") -> "JournalRecord": ...

    def has_intent(self, intent_id: str) -> bool: ...

    def verify(self) -> "IntegrityResult": ...
