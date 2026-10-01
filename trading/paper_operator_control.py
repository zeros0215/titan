"""Durable, fail-closed operator controls for the local Kiwoom paper pilot."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable


RELEASE_CONFIRMATION = "ENABLE_PAPER_PILOT"
_CONTROL_LOCK = threading.RLock()


def default_operator_control() -> dict:
    return {
        "schema_version": 1,
        "kill_switch_active": True,
        "updated_at": None,
        "updated_by": None,
        "approvals": [],
    }


class PaperOperatorControl:
    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = path
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def load(self) -> dict:
        with _CONTROL_LOCK:
            if not self.path.exists():
                return default_operator_control()
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                self._validate(value)
                return value
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                return default_operator_control()

    def set_kill_switch(
        self, active: bool, *, operator_ref: str, confirmation: str = ""
    ) -> dict:
        if not operator_ref.strip():
            raise ValueError("operator_ref is required")
        if not active and confirmation != RELEASE_CONFIRMATION:
            raise ValueError("explicit paper-pilot confirmation is required")
        with _CONTROL_LOCK:
            state = self.load()
            state["kill_switch_active"] = active
            state["updated_at"] = self.clock().isoformat()
            state["updated_by"] = operator_ref.strip()
            if active:
                state["approvals"] = []
            self._write(state)
            return state

    def decide(
        self,
        *,
        intent_id: str,
        approved: bool,
        operator_ref: str,
        ttl: timedelta = timedelta(seconds=30),
    ) -> dict:
        if not intent_id.strip() or not operator_ref.strip():
            raise ValueError("intent_id and operator_ref are required")
        if ttl <= timedelta(0) or ttl > timedelta(minutes=5):
            raise ValueError("approval ttl must be positive and at most five minutes")
        with _CONTROL_LOCK:
            state = self.load()
            if approved and state["kill_switch_active"]:
                raise ValueError("kill switch must be released before approval")
            now = self.clock()
            state["approvals"] = [
                item for item in state["approvals"]
                if item["intent_id"] != intent_id and datetime.fromisoformat(item["expires_at"]) > now
            ]
            state["approvals"].append({
                "intent_id": intent_id,
                "decision": "APPROVED" if approved else "REJECTED",
                "operator_ref": operator_ref.strip(),
                "decided_at": now.isoformat(),
                "expires_at": (now + ttl).isoformat(),
            })
            state["updated_at"] = now.isoformat()
            state["updated_by"] = operator_ref.strip()
            self._write(state)
            return state

    def consume_approval(self, intent_id: str) -> dict:
        """Atomically remove and return one valid approval for an intent."""
        if not intent_id.strip():
            raise ValueError("intent_id is required")
        with _CONTROL_LOCK:
            state = self.load()
            if state["kill_switch_active"]:
                raise ValueError("kill switch is active")
            now = self.clock()
            matching = next(
                (item for item in state["approvals"] if item["intent_id"] == intent_id),
                None,
            )
            state["approvals"] = [
                item for item in state["approvals"] if item["intent_id"] != intent_id
            ]
            if matching is not None:
                state["updated_at"] = now.isoformat()
                self._write(state)
            if matching is None:
                raise ValueError("operator approval is required")
            if matching["decision"] != "APPROVED":
                raise ValueError("operator rejected this intent")
            if datetime.fromisoformat(matching["expires_at"]) <= now:
                raise ValueError("operator approval expired")
            return matching

    def require_kill_switch_released(self) -> None:
        if self.load()["kill_switch_active"]:
            raise ValueError("kill switch is active")

    def _write(self, state: dict) -> None:
        self._validate(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _validate(state: dict) -> None:
        if state.get("schema_version") != 1:
            raise ValueError("unsupported operator-control schema")
        if not isinstance(state.get("kill_switch_active"), bool):
            raise TypeError("kill_switch_active must be boolean")
        if not isinstance(state.get("approvals"), list):
            raise TypeError("approvals must be a list")
        for item in state["approvals"]:
            if item.get("decision") not in {"APPROVED", "REJECTED"}:
                raise ValueError("invalid operator decision")
            for field in ("intent_id", "operator_ref", "decided_at", "expires_at"):
                if not str(item.get(field) or "").strip():
                    raise ValueError(f"{field} is required")
            decided = datetime.fromisoformat(item["decided_at"])
            expires = datetime.fromisoformat(item["expires_at"])
            if decided.tzinfo is None or expires.tzinfo is None or expires <= decided:
                raise ValueError("operator decision timestamps are invalid")
