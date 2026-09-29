"""Journal-first orchestration for broker-neutral order submission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from trading.journal import EventType, JournalEvent
from trading.model import BrokerOrder, Fill, OrderIntent, OrderStatus
from trading.ports import ExecutionBroker, ExecutionJournal
from trading.risk import RiskContext, RiskDecision, RiskManager


class SubmissionUncertainError(RuntimeError):
    """Submission began but the broker outcome cannot be proven."""


class PostSubmissionJournalError(RuntimeError):
    """The broker responded but its result could not be durably recorded."""


@dataclass(frozen=True, slots=True)
class CoordinationResult:
    decision: RiskDecision
    order: BrokerOrder | None
    fills: tuple[Fill, ...]


class OrderCoordinator:
    def __init__(
        self,
        broker: ExecutionBroker,
        journal: ExecutionJournal,
        risk_manager: RiskManager,
        *,
        clock: Callable[[], datetime] | None = None,
        event_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.broker = broker
        self.journal = journal
        self.risk_manager = risk_manager
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.event_id_factory = event_id_factory or (lambda: uuid4().hex)

    def submit(
        self, intent: OrderIntent, context: RiskContext
    ) -> CoordinationResult:
        if self.journal.has_intent(intent.intent_id):
            raise ValueError(f"intent already recorded: {intent.intent_id}")
        self._append(
            EventType.INTENT_RECORDED,
            intent.intent_id,
            {
                "strategy_version": intent.strategy_version,
                "symbol": intent.symbol,
                "side": intent.side,
                "quantity": intent.quantity,
                "order_type": intent.order_type,
                "limit_price": intent.limit_price,
                "rationale": intent.rationale,
            },
        )
        decision = self.risk_manager.evaluate(intent, context)
        self._append(
            EventType.RISK_DECIDED,
            intent.intent_id,
            {
                "approved": decision.approved,
                "reasons": [reason.value for reason in decision.reasons],
                "estimated_price": decision.estimated_price,
                "estimated_order_value": decision.estimated_order_value,
            },
        )
        if not decision.approved or decision.request is None:
            return CoordinationResult(decision, None, ())
        self._append(
            EventType.ORDER_SUBMISSION_STARTED,
            intent.intent_id,
            {
                "reserved_value": decision.estimated_order_value,
                "requested_quantity": intent.quantity,
            },
        )
        try:
            order = self.broker.submit_order(decision.request)
        except Exception as error:
            raise SubmissionUncertainError(
                f"submission outcome is unknown for {intent.intent_id}; do not retry"
            ) from error
        try:
            self._append(
                EventType.ORDER_ACCEPTED,
                intent.intent_id,
                {"broker_order_id": order.broker_order_id},
                aggregate_id=order.broker_order_id,
            )
            fills = self._broker_fills(order.broker_order_id)
            for fill in fills:
                self.record_fill(intent.intent_id, fill)
            if order.status in {OrderStatus.REJECTED, OrderStatus.CANCELLED}:
                self._append(
                    EventType.ORDER_STATUS_CHANGED,
                    intent.intent_id,
                    {
                        "status": order.status,
                        "filled_quantity": order.filled_quantity,
                    },
                    aggregate_id=order.broker_order_id,
                )
        except Exception as error:
            raise PostSubmissionJournalError(
                "broker result was not durably recorded; activate kill switch"
            ) from error
        return CoordinationResult(decision, order, fills)

    def record_fill(self, intent_id: str, fill: Fill) -> bool:
        if self.journal.has_fill(fill.fill_id):
            return False
        self._append(
            EventType.FILL_RECORDED,
            intent_id,
            {
                "fill_id": fill.fill_id,
                "quantity": fill.quantity,
                "price": fill.price,
                "fee": fill.fee,
                "filled_at": fill.filled_at,
            },
            aggregate_id=fill.broker_order_id,
            occurred_at=fill.filled_at,
        )
        return True

    def _broker_fills(self, broker_order_id: str) -> tuple[Fill, ...]:
        method = getattr(self.broker, "fills_for_order", None)
        return tuple(method(broker_order_id)) if method else ()

    def _append(
        self,
        event_type: EventType,
        intent_id: str,
        payload: dict,
        *,
        aggregate_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        self.journal.append(JournalEvent(
            self.event_id_factory(),
            event_type,
            occurred_at or self.clock(),
            payload,
            intent_id=intent_id,
            aggregate_id=aggregate_id,
        ))
