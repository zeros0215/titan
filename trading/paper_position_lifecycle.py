"""Deterministic S80 paper-position holding and exit-signal projection."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from trading.journal import EventType, SQLiteExecutionJournal


S80_STRATEGY_VERSIONS = {
    "V1.3-S80-N7-TP5-SL10-CANDIDATE",
    "V1.3-S80-OBSERVATION-PAPER",
}


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
            if str(event.payload.get("strategy_version")) in S80_STRATEGY_VERSIONS:
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


def realized_s80_performance(journal: SQLiteExecutionJournal) -> dict[str, object]:
    """Aggregate completed S80 round trips from durable fill events.

    Buy lots are matched FIFO by symbol. A completed trade is counted for each
    sell intent whose filled quantity can be fully matched to earlier buys.
    Recorded broker fees are deducted from realized P&L.
    """
    integrity = journal.verify()
    if not integrity.valid:
        return {
            "realized_pnl": Decimal("0"),
            "completed_trades": 0,
            "winning_trades": 0,
        }

    intents: dict[str, tuple[str, str]] = {}
    fills: dict[str, list[tuple[Decimal, int, Decimal]]] = {}
    for record in journal.records():
        event = record.event
        if event.event_type is EventType.INTENT_RECORDED and event.intent_id:
            if str(event.payload.get("strategy_version")) in S80_STRATEGY_VERSIONS:
                intents[event.intent_id] = (
                    str(event.payload.get("symbol") or ""),
                    str(event.payload.get("side") or ""),
                )
        elif event.event_type is EventType.FILL_RECORDED and event.intent_id in intents:
            fills.setdefault(event.intent_id, []).append((
                Decimal(str(event.payload.get("price") or "0")),
                int(event.payload.get("quantity") or 0),
                Decimal(str(event.payload.get("fee") or "0")),
            ))

    lots: dict[str, list[list[object]]] = {}
    realized = Decimal("0")
    completed = 0
    wins = 0
    for intent_id, (symbol, side) in intents.items():
        intent_fills = fills.get(intent_id, [])
        if not intent_fills:
            continue
        if side == "BUY":
            for price, quantity, fee in intent_fills:
                if price > 0 and quantity > 0:
                    lots.setdefault(symbol, []).append([quantity, price, fee])
            continue
        if side != "SELL":
            continue

        sell_quantity = sum(item[1] for item in intent_fills)
        available = sum(int(item[0]) for item in lots.get(symbol, []))
        if sell_quantity <= 0 or available < sell_quantity:
            continue
        proceeds = sum(price * quantity - fee for price, quantity, fee in intent_fills)
        cost = Decimal("0")
        remaining = sell_quantity
        symbol_lots = lots.setdefault(symbol, [])
        while remaining:
            quantity, price, fee = symbol_lots[0]
            matched = min(int(quantity), remaining)
            fee_share = Decimal(str(fee)) * matched / int(quantity)
            cost += Decimal(str(price)) * matched + fee_share
            if matched == int(quantity):
                symbol_lots.pop(0)
            else:
                symbol_lots[0] = [int(quantity) - matched, price, Decimal(str(fee)) - fee_share]
            remaining -= matched
        trade_pnl = proceeds - cost
        realized += trade_pnl
        completed += 1
        wins += trade_pnl > 0

    return {
        "realized_pnl": realized,
        "completed_trades": completed,
        "winning_trades": wins,
    }
