"""Fail-closed dashboard projection for Kiwoom paper trading."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STRATEGY_VERSION = "V1.3-S80-N7-TP5-SL10-CANDIDATE"
PAPER_BROKER = "KIWOOM"
PAPER_ENVIRONMENT = "MOCK"
SENSITIVE_PARTS = {"account", "password", "secret", "token", "authorization"}


def unavailable_paper_dashboard(reason: str = "PAPER_ENGINE_NOT_CONFIGURED") -> dict:
    """Return a safe initial view that can never imply trading readiness."""
    return {
        "mode": "PAPER",
        "broker": PAPER_BROKER,
        "environment": PAPER_ENVIRONMENT,
        "strategy_version": STRATEGY_VERSION,
        "connection": {
            "status": "DISCONNECTED",
            "authenticated": False,
            "last_sync_at": None,
        },
        "safety": {
            "new_orders_allowed": False,
            "kill_switch_active": True,
            "reconciliation_ready": False,
            "blocked_reasons": [reason],
        },
        "summary": {
            "cash": None,
            "buying_power": None,
            "market_value": "0",
            "realized_pnl": "0",
            "unrealized_pnl": "0",
            "completed_trades": 0,
            "winning_trades": 0,
        },
        "candidates": [],
        "positions": [],
        "orders": [],
        "updated_at": None,
    }


def load_paper_dashboard(path: Path) -> dict:
    """Load an engine-produced projection, rejecting unsafe or malformed state."""
    if not path.exists():
        return unavailable_paper_dashboard()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        _validate_projection(payload)
        return payload
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        return unavailable_paper_dashboard(
            f"PAPER_DASHBOARD_INVALID:{type(error).__name__}"
        )


def write_paper_dashboard(path: Path, payload: dict) -> None:
    """Atomically publish a validated, non-secret projection for the UI."""
    _validate_projection(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _validate_projection(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise TypeError("paper dashboard projection must be an object")
    if payload.get("mode") != "PAPER":
        raise ValueError("paper dashboard mode must be PAPER")
    if payload.get("broker") != PAPER_BROKER:
        raise ValueError("paper dashboard broker must be KIWOOM")
    if payload.get("environment") != PAPER_ENVIRONMENT:
        raise ValueError("paper dashboard environment must be MOCK")
    if payload.get("strategy_version") != STRATEGY_VERSION:
        raise ValueError("unexpected paper strategy version")
    _reject_sensitive_keys(payload)
    connection = payload["connection"]
    safety = payload["safety"]
    summary = payload["summary"]
    if not isinstance(connection, dict) or not isinstance(safety, dict):
        raise TypeError("connection and safety must be objects")
    if not isinstance(summary, dict):
        raise TypeError("summary must be an object")
    if not isinstance(safety.get("new_orders_allowed"), bool):
        raise TypeError("new_orders_allowed must be boolean")
    if not isinstance(safety.get("kill_switch_active"), bool):
        raise TypeError("kill_switch_active must be boolean")
    if not isinstance(safety.get("reconciliation_ready"), bool):
        raise TypeError("reconciliation_ready must be boolean")
    if not isinstance(safety.get("blocked_reasons"), list):
        raise TypeError("blocked_reasons must be a list")
    for field in ("candidates", "positions", "orders"):
        if not isinstance(payload.get(field), list):
            raise TypeError(f"{field} must be a list")
    updated_at = payload.get("updated_at")
    if updated_at is not None:
        parsed = datetime.fromisoformat(str(updated_at))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")


def _reject_sensitive_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            parts = set(normalized.split("_"))
            if normalized != "account_ref" and parts & SENSITIVE_PARTS:
                raise ValueError(f"sensitive dashboard field is forbidden: {key}")
            _reject_sensitive_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive_keys(child)


def example_paper_dashboard() -> dict:
    """Small valid projection useful to adapters and contract tests."""
    value = unavailable_paper_dashboard("AWAITING_FIRST_RECONCILIATION")
    value["updated_at"] = datetime.now(timezone.utc).isoformat()
    return value
