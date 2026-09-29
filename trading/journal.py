"""SQLite append-only execution journal with a verifiable hash chain."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from trading.model import TradingMode


GENESIS_HASH = "0" * 64
SCHEMA_VERSION = 1
SENSITIVE_KEYS = {
    "account", "account_number", "account_no", "app_key", "app_secret",
    "authorization", "password", "secret", "secret_key", "token",
    "access_token", "refresh_token",
}


class JournalError(RuntimeError):
    pass


class JournalBindingError(JournalError):
    pass


class JournalIntegrityError(JournalError):
    pass


class DuplicateIntentError(JournalError):
    pass


class EventType(str, Enum):
    INTENT_RECORDED = "INTENT_RECORDED"
    RISK_DECIDED = "RISK_DECIDED"
    ORDER_SUBMISSION_STARTED = "ORDER_SUBMISSION_STARTED"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_STATUS_CHANGED = "ORDER_STATUS_CHANGED"
    FILL_RECORDED = "FILL_RECORDED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"
    KILL_SWITCH_CHANGED = "KILL_SWITCH_CHANGED"
    OPERATOR_ACTION = "OPERATOR_ACTION"


@dataclass(frozen=True, slots=True)
class JournalEvent:
    event_id: str
    event_type: EventType
    occurred_at: datetime
    payload: dict[str, Any]
    intent_id: str | None = None
    aggregate_id: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id is required")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.intent_id is not None and not self.intent_id.strip():
            raise ValueError("intent_id must not be blank")
        if self.event_type is EventType.INTENT_RECORDED and not self.intent_id:
            raise ValueError("INTENT_RECORDED requires intent_id")


@dataclass(frozen=True, slots=True)
class JournalRecord:
    sequence: int
    stream_id: str
    event: JournalEvent
    previous_hash: str
    event_hash: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class IntegrityResult:
    valid: bool
    event_count: int
    last_hash: str
    error: str | None = None


class SQLiteExecutionJournal:
    """One durable journal bound to exactly one mode and account alias."""

    def __init__(
        self,
        path: Path,
        *,
        mode: TradingMode,
        account_ref: str,
    ) -> None:
        if not account_ref.strip() or _looks_like_account_number(account_ref):
            raise ValueError(
                "account_ref must be a non-sensitive alias or hash, not an account number"
            )
        self.path = path
        self.mode = mode
        self.account_ref = account_ref
        self.stream_id = f"{mode.value}:{account_ref}"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def append(self, event: JournalEvent) -> JournalRecord:
        payload = _canonical_payload(event.payload)
        occurred_at = event.occurred_at.isoformat()
        recorded_at = datetime.now(timezone.utc)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            last = connection.execute(
                "SELECT sequence, event_hash FROM journal_events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            sequence = (int(last[0]) + 1) if last else 1
            previous_hash = str(last[1]) if last else GENESIS_HASH
            event_hash = _event_hash(
                self.stream_id,
                sequence,
                event.event_id,
                event.event_type.value,
                occurred_at,
                event.intent_id,
                event.aggregate_id,
                payload,
                previous_hash,
            )
            try:
                connection.execute(
                    """
                    INSERT INTO journal_events (
                        sequence, event_id, event_type, occurred_at, intent_id,
                        aggregate_id, payload_json, previous_hash, event_hash,
                        recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence, event.event_id, event.event_type.value,
                        occurred_at, event.intent_id, event.aggregate_id,
                        payload, previous_hash, event_hash,
                        recorded_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                message = str(error)
                if "journal_events.intent_id" in message:
                    raise DuplicateIntentError(event.intent_id or "") from error
                raise JournalError(message) from error
        return JournalRecord(
            sequence, self.stream_id, event, previous_hash, event_hash, recorded_at
        )

    def has_intent(self, intent_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM journal_events "
                "WHERE event_type=? AND intent_id=? LIMIT 1",
                (EventType.INTENT_RECORDED.value, intent_id),
            ).fetchone()
        return row is not None

    def has_fill(self, fill_id: str) -> bool:
        """Return whether a fill callback was already durably recorded."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM journal_events "
                "WHERE event_type=?",
                (EventType.FILL_RECORDED.value,),
            ).fetchall()
        return any(
            str(json.loads(row[0]).get("fill_id") or "") == fill_id
            for row in rows
        )

    def records(self) -> tuple[JournalRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT sequence, event_id, event_type, occurred_at, intent_id, "
                "aggregate_id, payload_json, previous_hash, event_hash, recorded_at "
                "FROM journal_events ORDER BY sequence"
            ).fetchall()
        records = []
        for row in rows:
            records.append(JournalRecord(
                sequence=int(row[0]),
                stream_id=self.stream_id,
                event=JournalEvent(
                    event_id=str(row[1]),
                    event_type=EventType(row[2]),
                    occurred_at=datetime.fromisoformat(row[3]),
                    intent_id=row[4],
                    aggregate_id=row[5],
                    payload=json.loads(row[6]),
                ),
                previous_hash=str(row[7]),
                event_hash=str(row[8]),
                recorded_at=datetime.fromisoformat(row[9]),
            ))
        return tuple(records)

    def verify(self) -> IntegrityResult:
        previous_hash = GENESIS_HASH
        expected_sequence = 1
        try:
            records = self.records()
            for record in records:
                if record.sequence != expected_sequence:
                    raise JournalIntegrityError(
                        f"sequence gap at {expected_sequence}"
                    )
                if record.previous_hash != previous_hash:
                    raise JournalIntegrityError(
                        f"previous hash mismatch at {record.sequence}"
                    )
                payload = _canonical_payload(record.event.payload)
                expected_hash = _event_hash(
                    self.stream_id,
                    record.sequence,
                    record.event.event_id,
                    record.event.event_type.value,
                    record.event.occurred_at.isoformat(),
                    record.event.intent_id,
                    record.event.aggregate_id,
                    payload,
                    previous_hash,
                )
                if record.event_hash != expected_hash:
                    raise JournalIntegrityError(
                        f"event hash mismatch at {record.sequence}"
                    )
                previous_hash = record.event_hash
                expected_sequence += 1
        except (JournalError, ValueError, KeyError, json.JSONDecodeError) as error:
            return IntegrityResult(
                False, expected_sequence - 1, previous_hash, str(error)
            )
        return IntegrityResult(True, len(records), previous_hash)

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS journal_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL,
                    stream_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    account_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS journal_events (
                    sequence INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    intent_id TEXT,
                    aggregate_id TEXT,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE,
                    recorded_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_intent_event
                    ON journal_events(intent_id)
                    WHERE event_type = 'INTENT_RECORDED';
                CREATE TRIGGER IF NOT EXISTS journal_events_no_update
                    BEFORE UPDATE ON journal_events
                    BEGIN SELECT RAISE(ABORT, 'journal events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS journal_events_no_delete
                    BEFORE DELETE ON journal_events
                    BEGIN SELECT RAISE(ABORT, 'journal events are append-only'); END;
            """)
            metadata = connection.execute(
                "SELECT schema_version, stream_id, mode, account_ref "
                "FROM journal_metadata WHERE singleton=1"
            ).fetchone()
            if metadata is None:
                connection.execute(
                    "INSERT INTO journal_metadata VALUES (1, ?, ?, ?, ?, ?)",
                    (
                        SCHEMA_VERSION, self.stream_id, self.mode.value,
                        self.account_ref, datetime.now(timezone.utc).isoformat(),
                    ),
                )
            elif metadata != (
                SCHEMA_VERSION, self.stream_id, self.mode.value, self.account_ref
            ):
                raise JournalBindingError(
                    "journal is bound to a different schema, mode, or account"
                )

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                yield connection
        finally:
            connection.close()


def _looks_like_account_number(value: str) -> bool:
    compact = value.replace("-", "").replace(" ", "")
    return compact.isdigit() and len(compact) >= 8


def _canonical_payload(payload: dict[str, Any]) -> str:
    normalized = _normalize(payload)
    return json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _normalize(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            text_key = str(key)
            if _is_sensitive_key(text_key):
                raise ValueError(
                    f"sensitive field is not allowed in journal payload: {text_key}"
                )
            result[text_key] = _normalize(item, (*path, text_key))
        return result
    if isinstance(value, (list, tuple)):
        return [_normalize(item, path) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("journal datetime values must be timezone-aware")
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        raise ValueError("float is not allowed in financial journal payloads")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported journal payload type at {'.'.join(path)}")


def _is_sensitive_key(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    if normalized == "account_ref":
        return False
    if normalized in SENSITIVE_KEYS:
        return True
    parts = set(normalized.split("_"))
    return bool(parts & {"password", "secret", "token", "authorization"})


def _event_hash(
    stream_id: str,
    sequence: int,
    event_id: str,
    event_type: str,
    occurred_at: str,
    intent_id: str | None,
    aggregate_id: str | None,
    payload_json: str,
    previous_hash: str,
) -> str:
    canonical = json.dumps(
        {
            "aggregate_id": aggregate_id,
            "event_id": event_id,
            "event_type": event_type,
            "intent_id": intent_id,
            "occurred_at": occurred_at,
            "payload": json.loads(payload_json),
            "previous_hash": previous_hash,
            "sequence": sequence,
            "stream_id": stream_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
