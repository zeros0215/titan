"""Deterministic S80 paper-position holding and exit-signal projection."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from trading.journal import EventType, SQLiteExecutionJournal


def holding_sessions(opened_on: date, as_of: date) -> int:
    if opened_on > as_of:
        raise ValueError("position open date cannot be in the future")
    cursor = opened_on
    count = 0
    while cursor < as_of:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            count += 1
    return count


def exit_signal(
    entry_price: Decimal,
    current_price: Decimal,
    sessions: int,
) -> str | None:
    if entry_price <= 0 or current_price <= 0:
        raise ValueError("position prices must be positive")
    if sessions < 0:
        raise ValueError("holding sessions must not be negative")
    if current_price <= entry_price * Decimal("0.90"):
        return "STOP_LOSS"
    if current_price >= entry_price * Decimal("1.05"):
        return "TAKE_PROFIT"
    if sessions >= 20:
        return "MAX_HOLDING"
    return None


def managed_s80_positions(journal: SQLiteExecutionJournal) -> dict[str, str]:
    """Return symbol-to-strategy ownership for open accepted S80 paper buys."""
    integrity = journal.verify()
    if not integrity.valid:
        return {}
    intents: dict[str, tuple[str, str, str]] = {}
    managed: dict[str, str] = {}
    for record in journal.records():
        event = record.event
        if event.event_type is EventType.INTENT_RECORDED and event.intent_id:
            if str(event.payload.get("strategy_version")) in {
                "V1.3-S80-N7-TP5-SL10-CANDIDATE",
                "V1.3-S80-OBSERVATION-PAPER",
            }:
                intents[event.intent_id] = (
                    str(event.payload.get("symbol") or ""),
                    str(event.payload.get("side") or ""),
                    str(event.payload.get("strategy_version") or ""),
                )
        elif event.event_type is EventType.ORDER_ACCEPTED and event.intent_id in intents:
            symbol, side, strategy_version = intents[event.intent_id]
            if side == "BUY":
                managed[symbol] = strategy_version
            elif side == "SELL":
                managed.pop(symbol, None)
    return managed


def managed_s80_symbols(journal: SQLiteExecutionJournal) -> set[str]:
    return set(managed_s80_positions(journal))
