"""Durable fail-closed operating mode for S80 paper automation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODES = frozenset({"OFF", "SHADOW", "AUTO_BUY", "AUTO_TRADE"})
CONFIRMATIONS = {
    "SHADOW": "ENABLE_PAPER_SHADOW",
    "AUTO_BUY": "ENABLE_PAPER_AUTO_BUY",
    "AUTO_TRADE": "ENABLE_PAPER_AUTO_TRADE",
}


class PaperAutomationControl:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("mode") not in MODES:
                raise ValueError
            return value
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {
                "schema_version": 1, "mode": "OFF", "updated_at": None,
                "updated_by": "fail-closed", "last_cycle_at": None,
                "last_action": None, "last_error": None,
            }

    def set_mode(self, mode: str, *, operator_ref: str, confirmation: str = "") -> dict:
        mode = str(mode).upper()
        if mode not in MODES:
            raise ValueError("unsupported paper automation mode")
        if not operator_ref.strip():
            raise ValueError("operator_ref is required")
        if mode != "OFF" and confirmation != CONFIRMATIONS[mode]:
            raise ValueError(f"exact confirmation is required: {CONFIRMATIONS[mode]}")
        state = self.load()
        state.update({
            "schema_version": 1,
            "mode": mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": operator_ref.strip(),
            "last_error": None,
        })
        self._write(state)
        return state

    def record_cycle(self, *, action: str | None, error: str | None = None) -> dict:
        state = self.load()
        state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
        state["last_action"] = action
        state["last_error"] = error
        self._write(state)
        return state

    def _write(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)


def select_automatic_action(
    state: dict[str, Any], mode: str, *, hour: int, minute: int
) -> tuple[str, str] | None:
    """Choose one action, always prioritizing exits over new exposure."""
    if mode == "AUTO_TRADE":
        position = next((
            item for item in state.get("positions", [])
            if item.get("exit_approval_enabled") and item.get("exit_intent_id")
        ), None)
        if position is not None:
            return "SELL", str(position["exit_intent_id"])
    if mode in {"AUTO_BUY", "AUTO_TRADE"} and (hour, minute) <= (10, 0):
        candidate = next((
            item for item in state.get("candidates", [])
            if item.get("eligible") and item.get("approval_enabled")
            and item.get("intent_id")
        ), None)
        if candidate is not None:
            return "BUY", str(candidate["intent_id"])
    return None
