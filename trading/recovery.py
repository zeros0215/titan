"""Replay execution journal events into fail-closed restart state."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading.journal import EventType, SQLiteExecutionJournal
from trading.model import OrderStatus


ACTIVE_STATUSES = {
    OrderStatus.PENDING_SUBMIT,
    OrderStatus.ACCEPTED,
    OrderStatus.PARTIALLY_FILLED,
    OrderStatus.CANCEL_PENDING,
    OrderStatus.UNKNOWN,
}
TERMINAL_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
}


@dataclass(frozen=True, slots=True)
class RecoveredOrder:
    intent_id: str
    broker_order_id: str | None
    status: OrderStatus
    reserved_value: Decimal
    requested_quantity: int
    filled_quantity: int


@dataclass(frozen=True, slots=True)
class RecoveredExecutionState:
    safe_to_trade: bool
    blocked_reasons: tuple[str, ...]
    seen_intent_ids: frozenset[str]
    open_orders: tuple[RecoveredOrder, ...]
    reserved_buying_power: Decimal
    kill_switch_active: bool
    reconciliation_ready: bool
    event_count: int
    last_event_hash: str


def recover_execution_state(
    journal: SQLiteExecutionJournal,
    *,
    recovery_id: str,
) -> RecoveredExecutionState:
    if not recovery_id.strip():
        raise ValueError("recovery_id is required")
    integrity = journal.verify()
    if not integrity.valid:
        return RecoveredExecutionState(
            False,
            (f"JOURNAL_INTEGRITY_FAILED:{integrity.error}",),
            frozenset(),
            (),
            Decimal("0"),
            True,
            False,
            integrity.event_count,
            integrity.last_hash,
        )

    intents: set[str] = set()
    orders: dict[str, dict] = {}
    kill_switch = False
    reconciliation_ready = False
    uncertain_intents: set[str] = set()
    approved_intents: set[str] = set()
    fill_ids: set[str] = set()
    broker_order_ids: set[str] = set()
    semantic_errors: list[str] = []

    for record in journal.records():
        event = record.event
        payload = event.payload
        intent_id = event.intent_id
        try:
            if event.event_type is EventType.INTENT_RECORDED:
                intents.add(_required_text(intent_id, "intent_id"))
            elif event.event_type is EventType.RISK_DECIDED:
                key = _required_text(intent_id, "intent_id")
                if key not in intents:
                    raise ValueError("risk decision references unknown intent")
                if _required_bool(payload.get("approved"), "approved"):
                    approved_intents.add(key)
                else:
                    approved_intents.discard(key)
            elif event.event_type is EventType.ORDER_SUBMISSION_STARTED:
                key = _required_text(intent_id, "intent_id")
                if key not in intents:
                    raise ValueError("submission references unknown intent")
                if key not in approved_intents:
                    raise ValueError("submission has no approved risk decision")
                if key in orders:
                    raise ValueError("intent has more than one submission")
                uncertain_intents.add(key)
                orders[key] = {
                    "intent_id": key,
                    "broker_order_id": None,
                    "status": OrderStatus.UNKNOWN,
                    "reserved_value": Decimal(str(payload["reserved_value"])),
                    "requested_quantity": int(payload["requested_quantity"]),
                    "filled_quantity": 0,
                }
            elif event.event_type is EventType.ORDER_ACCEPTED:
                key = _required_text(intent_id, "intent_id")
                if key not in orders:
                    raise ValueError("accepted order has no submission event")
                uncertain_intents.discard(key)
                order = orders[key]
                if order["broker_order_id"] is not None:
                    raise ValueError("order has more than one acceptance")
                broker_order_id = _required_text(
                    payload.get("broker_order_id"), "broker_order_id"
                )
                if broker_order_id in broker_order_ids:
                    raise ValueError("duplicate broker_order_id")
                broker_order_ids.add(broker_order_id)
                order["broker_order_id"] = broker_order_id
                order["status"] = OrderStatus.ACCEPTED
            elif event.event_type is EventType.ORDER_STATUS_CHANGED:
                key = _required_text(intent_id, "intent_id")
                if key not in orders:
                    raise ValueError("status references unknown order")
                order = orders[key]
                order["status"] = OrderStatus(payload["status"])
                order["filled_quantity"] = int(payload["filled_quantity"])
                _validate_quantity(order)
            elif event.event_type is EventType.FILL_RECORDED:
                key = _required_text(intent_id, "intent_id")
                if key not in orders:
                    raise ValueError("fill references unknown order")
                order = orders[key]
                fill_id = _required_text(payload.get("fill_id"), "fill_id")
                if fill_id in fill_ids:
                    raise ValueError("duplicate fill_id")
                fill_ids.add(fill_id)
                order["filled_quantity"] += int(payload["quantity"])
                _validate_quantity(order)
                if order["filled_quantity"] == order["requested_quantity"]:
                    order["status"] = OrderStatus.FILLED
                else:
                    order["status"] = OrderStatus.PARTIALLY_FILLED
            elif event.event_type is EventType.KILL_SWITCH_CHANGED:
                kill_switch = _required_bool(payload.get("active"), "active")
            elif event.event_type is EventType.RECONCILIATION_COMPLETED:
                event_recovery_id = _required_text(
                    payload.get("recovery_id"), "recovery_id"
                )
                reconciliation_ready = (
                    event_recovery_id == recovery_id
                    and _required_bool(payload.get("ready"), "ready")
                )
        except (KeyError, TypeError, ValueError) as error:
            semantic_errors.append(f"EVENT_{record.sequence}:{error}")

    recovered_orders = tuple(
        RecoveredOrder(**order)
        for _, order in sorted(orders.items())
        if order["status"] in ACTIVE_STATUSES
    )
    reserved = sum(
        (order.reserved_value for order in recovered_orders), Decimal("0")
    )
    reasons = list(semantic_errors)
    if not reconciliation_ready:
        reasons.append("ACCOUNT_RECONCILIATION_REQUIRED")
    if kill_switch:
        reasons.append("KILL_SWITCH_ACTIVE")
    if uncertain_intents:
        reasons.append(
            "UNCERTAIN_SUBMISSIONS:" + ",".join(sorted(uncertain_intents))
        )
    return RecoveredExecutionState(
        not reasons,
        tuple(reasons),
        frozenset(intents),
        recovered_orders,
        reserved,
        kill_switch,
        reconciliation_ready,
        integrity.event_count,
        integrity.last_hash,
    )


def _required_text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _required_bool(value, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _validate_quantity(order: dict) -> None:
    if not 0 <= order["filled_quantity"] <= order["requested_quantity"]:
        raise ValueError("filled quantity is outside requested quantity")
