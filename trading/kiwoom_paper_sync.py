"""Build the read-only dashboard projection from a Kiwoom mock account."""

from __future__ import annotations

import json
from decimal import Decimal
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from broker.kiwoom import KiwoomPaperClient, KiwoomPaperCredentials
from trading.paper_dashboard import (
    STRATEGY_VERSION, load_paper_dashboard, write_paper_dashboard,
)
from trading.s80_paper_candidates import (
    build_s80_paper_candidates,
    load_latest_s80_selection,
)
from trading.paper_position_lifecycle import (
    exit_signal, holding_sessions, managed_s80_positions,
    realized_s80_performance,
)
from trading.journal import EventType, JournalEvent, SQLiteExecutionJournal
from trading.model import TradingMode


SEOUL = ZoneInfo("Asia/Seoul")


def synchronize_kiwoom_paper_dashboard(
    path: Path,
    *,
    selection_runs: Path = Path("output/kis_v1_1/runs"),
    journal_path: Path = Path("output/kiwoom_paper/s80_orders.sqlite"),
    client: KiwoomPaperClient | None = None,
    active_data_path: Path = Path("output/release/backtest_data.json"),
) -> dict:
    owns_client = client is None
    client = client or KiwoomPaperClient(KiwoomPaperCredentials.from_environment())
    previous_state = load_paper_dashboard(path)
    journal = SQLiteExecutionJournal(
        journal_path, mode=TradingMode.PAPER, account_ref="kiwoom_paper"
    )
    managed_positions = managed_s80_positions(journal)
    try:
        snapshot = client.account_snapshot()
        today = snapshot.synchronized_at.astimezone(SEOUL)
        orders = client.order_fill_details(order_date=today)
        _record_reconciled_fills(journal, orders)
        performance = realized_s80_performance(journal)
        selection = load_latest_s80_selection(
            selection_runs, today.date(),
            expected_selection_date=_active_coverage_end(active_data_path),
        )
        selected = (
            selection.get("selected_candidates", [])
            + selection.get("observation_candidates", [])
            if selection else []
        )
        quotes = {
            str(item.get("code") or "").zfill(6): client.stock_info(
                str(item.get("code") or "").zfill(6)
            )
            for item in selected
        }
    finally:
        if owns_client:
            client.close()
    projection = {
        "mode": "PAPER",
        "broker": "KIWOOM",
        "environment": "MOCK",
        "strategy_version": STRATEGY_VERSION,
        "connection": {
            "status": "CONNECTED",
            "authenticated": True,
            "last_sync_at": snapshot.synchronized_at.isoformat(),
        },
        "safety": {
            "new_orders_allowed": False,
            "kill_switch_active": True,
            "reconciliation_ready": True,
            "blocked_reasons": (
                ["AUTOMATIC_SUBMISSION_DISABLED"]
                if selection is not None
                else ["S80_SELECTION_NOT_READY", "AUTOMATIC_SUBMISSION_DISABLED"]
            ),
        },
        "selection": {
            "ready": selection is not None,
            "status": "PASS" if selection is not None else "MISSING_OR_STALE",
            "as_of": str(selection.get("as_of"))[:10] if selection else None,
            "strategy_version": (
                selection.get("strategy_version") if selection else None
            ),
        },
        "summary": {
            "cash": str(snapshot.cash),
            "buying_power": str(snapshot.buying_power),
            "market_value": str(snapshot.market_value),
            "realized_pnl": str(performance["realized_pnl"]),
            "unrealized_pnl": str(snapshot.unrealized_pnl),
            "completed_trades": performance["completed_trades"],
            "winning_trades": performance["winning_trades"],
        },
        "candidates": build_s80_paper_candidates(
            selection,
            quotes,
            held_symbols={item.code for item in snapshot.positions},
            ordered_symbols={item.symbol for item in orders},
        ),
        "positions": [
            _position_projection(
                item, orders, previous_state, snapshot.synchronized_at,
                managed_positions.get(item.code),
            )
            for item in snapshot.positions
        ],
        "orders": [
            {
                "time": item.ordered_at.isoformat(),
                "code": item.symbol,
                "name": item.symbol,
                "side": item.side.value,
                "requested_quantity": item.requested_quantity,
                "filled_quantity": item.filled_quantity,
                "fill_price": str(item.order_price),
                "status": (
                    "FILLED" if item.remaining_quantity == 0 else "OPEN"
                ),
                "reason": "BROKER_RECONCILIATION",
            }
            for item in orders
        ],
        "updated_at": snapshot.synchronized_at.isoformat(),
    }
    write_paper_dashboard(path, projection)
    return projection


def _record_reconciled_fills(
    journal: SQLiteExecutionJournal, orders,
) -> None:
    """Append newly observed broker fills for journal-owned paper orders."""
    records = journal.records()
    accepted = {
        record.event.aggregate_id: record.event.intent_id
        for record in records
        if record.event.event_type is EventType.ORDER_ACCEPTED
        and record.event.aggregate_id
        and record.event.intent_id
    }
    recorded: dict[str, int] = {}
    for record in records:
        if record.event.event_type is EventType.FILL_RECORDED:
            order_id = record.event.aggregate_id or ""
            recorded[order_id] = recorded.get(order_id, 0) + int(
                record.event.payload["quantity"]
            )
    for order in orders:
        intent_id = accepted.get(order.broker_order_id)
        previous = recorded.get(order.broker_order_id, 0)
        delta = order.filled_quantity - previous
        if intent_id is None or delta <= 0 or order.order_price <= 0:
            continue
        fill_id = f"kiwoom:{order.broker_order_id}:cumulative:{order.filled_quantity}"
        journal.append(JournalEvent(
            event_id=uuid5(NAMESPACE_URL, fill_id).hex,
            event_type=EventType.FILL_RECORDED,
            occurred_at=order.ordered_at,
            intent_id=intent_id,
            aggregate_id=order.broker_order_id,
            payload={
                "fill_id": fill_id,
                "quantity": delta,
                "price": order.order_price,
                "fee": "0",
                "filled_at": order.ordered_at,
                "source": "KIWOOM_ORDER_RECONCILIATION",
            },
        ))


def _active_coverage_end(active_data_path: Path) -> date | None:
    try:
        active = json.loads(active_data_path.read_text(encoding="utf-8"))
        manifest = json.loads(
            (Path(active["price_dir"]) / "price_history_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        return date.fromisoformat(manifest["coverage_end"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _position_projection(
    item, orders, previous_state: dict, observed_at,
    managed_strategy_version: str | None,
) -> dict:
    managed = managed_strategy_version is not None
    previous = next(
        (row for row in previous_state.get("positions", [])
         if row.get("code") == item.code and row.get("opened_on")),
        None,
    )
    buy_orders = [
        order for order in orders
        if order.symbol == item.code and order.side.value == "BUY"
    ]
    if previous is not None:
        opened_on = date.fromisoformat(previous["opened_on"])
        opened_source = previous.get("opened_on_source", "PRESERVED")
    elif buy_orders:
        opened_on = min(order.ordered_at for order in buy_orders).date()
        opened_source = "BROKER_ORDER"
    else:
        opened_on = observed_at.astimezone(SEOUL).date()
        opened_source = "FIRST_OBSERVED"
    sessions = holding_sessions(opened_on, observed_at.astimezone(SEOUL).date())
    signal = exit_signal(item.entry_price, item.current_price, sessions) if managed else None
    exit_intent_id = (
        f"s80-exit-{opened_on.isoformat()}-{item.code}-{signal.lower()}"
        if signal else None
    )
    manual_exit_intent_id = (
        f"s80-manual-exit-{observed_at.astimezone(SEOUL).date().isoformat()}-{item.code}"
        if managed and item.quantity == 1 and item.sellable_quantity >= 1
        else None
    )
    return {
        "code": item.code,
        "name": item.name,
        "quantity": item.quantity,
        "sellable_quantity": item.sellable_quantity,
        "entry_price": str(item.entry_price),
        "current_price": str(item.current_price),
        "market_value": str(item.market_value),
        "unrealized_pnl": str(item.unrealized_pnl),
        "return_rate": str(item.return_rate),
        "take_profit_price": str(item.entry_price * Decimal("1.05")),
        "stop_loss_price": str(item.entry_price * Decimal("0.90")),
        "opened_on": opened_on.isoformat(),
        "opened_on_source": opened_source,
        "holding_sessions": sessions,
        "exit_signal": signal,
        "managed_by_s80": managed,
        "cohort": (
            "OBSERVATION"
            if managed_strategy_version == "V1.3-S80-OBSERVATION-PAPER"
            else "SELECTED" if managed else None
        ),
        "strategy_version": managed_strategy_version,
        "exit_intent_id": exit_intent_id,
        "exit_approval_enabled": bool(exit_intent_id),
        "manual_exit_intent_id": manual_exit_intent_id,
        "manual_exit_enabled": bool(manual_exit_intent_id),
        "status": (
            f"EXIT_SIGNAL:{signal}" if signal else
            "HOLDING" if managed else "UNMANAGED"
        ),
    }
