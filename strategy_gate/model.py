from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json


class CandidateStatus(str, Enum):
    PROPOSED = "PROPOSED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    APPROVED = "APPROVED"


@dataclass(slots=True, frozen=True)
class AuditEvent:
    occurred_at: datetime
    action: str
    actor: str
    details: str
    previous_hash: str
    event_hash: str

    @classmethod
    def create(
        cls,
        action: str,
        actor: str,
        details: str,
        previous_hash: str = "",
        occurred_at: datetime | None = None,
    ):
        occurred_at = occurred_at or datetime.now()
        payload = {
            "occurred_at": occurred_at.isoformat(),
            "action": action,
            "actor": actor,
            "details": details,
            "previous_hash": previous_hash,
        }
        event_hash = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            occurred_at,
            action,
            actor,
            details,
            previous_hash,
            event_hash,
        )


@dataclass(slots=True)
class StrategyCandidate:
    candidate_version: str
    base_version: str
    description: str
    config: dict
    config_hash: str
    status: CandidateStatus
    created_at: datetime
    comparison: dict | None = None
    gate_checks: list[dict] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)
    approved_at: datetime | None = None
    approved_by: str | None = None
