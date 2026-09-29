"""Build the read-only dashboard projection from a Kiwoom mock account."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from broker.kiwoom import KiwoomPaperClient, KiwoomPaperCredentials
from trading.paper_dashboard import STRATEGY_VERSION, write_paper_dashboard


def synchronize_kiwoom_paper_dashboard(path: Path) -> dict:
    client = KiwoomPaperClient(KiwoomPaperCredentials.from_environment())
    try:
        snapshot = client.account_snapshot()
    finally:
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
            "blocked_reasons": ["ORDER_EXECUTION_NOT_IMPLEMENTED"],
        },
        "summary": {
            "cash": str(snapshot.cash),
            "buying_power": str(snapshot.buying_power),
            "market_value": str(snapshot.market_value),
            "realized_pnl": None,
            "unrealized_pnl": str(snapshot.unrealized_pnl),
            "completed_trades": 0,
            "winning_trades": 0,
        },
        "candidates": [],
        "positions": [
            {
                "code": item.code,
                "name": item.name,
                "quantity": item.quantity,
                "sellable_quantity": item.sellable_quantity,
                "entry_price": str(item.entry_price),
                "current_price": str(item.current_price),
                "market_value": str(item.market_value),
                "unrealized_pnl": str(item.unrealized_pnl),
                "return_rate": str(item.return_rate),
                "take_profit_price": str(
                    item.entry_price * Decimal("1.05")
                ),
                "stop_loss_price": str(
                    item.entry_price * Decimal("0.90")
                ),
                "holding_sessions": None,
                "status": "BROKER_POSITION",
            }
            for item in snapshot.positions
        ],
        "orders": [],
        "updated_at": snapshot.synchronized_at.isoformat(),
    }
    write_paper_dashboard(path, projection)
    return projection
