import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from config.constants import OUTPUT_DIR, VERSION
from strategy_gate.model import AuditEvent, CandidateStatus, StrategyCandidate


class StrategyCandidateRepository:
    VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or OUTPUT_DIR / "strategy_candidates"

    def propose(
        self,
        candidate_version: str,
        description: str,
        config: dict,
        actor: str,
        base_version: str = VERSION,
    ) -> StrategyCandidate:
        self._validate_version(candidate_version)
        if candidate_version == base_version:
            raise ValueError("candidate version must differ from base version")
        if self.exists(candidate_version):
            raise ValueError(f"candidate already exists: {candidate_version}")
        if not description.strip():
            raise ValueError("description is required")
        if not actor.strip():
            raise ValueError("actor is required")
        candidate = StrategyCandidate(
            candidate_version=candidate_version,
            base_version=base_version,
            description=description.strip(),
            config=config,
            config_hash=self.fingerprint(config),
            status=CandidateStatus.PROPOSED,
            created_at=datetime.now(),
            audit_events=[
                AuditEvent.create("PROPOSED", actor.strip(), description.strip())
            ],
        )
        self.save(candidate)
        return candidate

    def save(self, candidate: StrategyCandidate) -> Path:
        self._validate_version(candidate.candidate_version)
        if candidate.config_hash != self.fingerprint(candidate.config):
            raise ValueError("candidate config does not match immutable hash")
        self._validate_audit_chain(candidate.audit_events)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(candidate.candidate_version)
        path.write_text(
            json.dumps(
                asdict(candidate),
                ensure_ascii=False,
                indent=2,
                default=self._json_default,
            ),
            encoding="utf-8",
        )
        return path

    def load(self, version: str) -> StrategyCandidate:
        self._validate_version(version)
        path = self._path(version)
        if not path.exists():
            raise FileNotFoundError(f"strategy candidate not found: {version}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidate = StrategyCandidate(
            candidate_version=payload["candidate_version"],
            base_version=payload["base_version"],
            description=payload["description"],
            config=payload["config"],
            config_hash=payload["config_hash"],
            status=CandidateStatus(payload["status"]),
            created_at=datetime.fromisoformat(payload["created_at"]),
            comparison=payload.get("comparison"),
            gate_checks=payload.get("gate_checks", []),
            audit_events=[
                AuditEvent(
                    datetime.fromisoformat(item["occurred_at"]),
                    item["action"],
                    item["actor"],
                    item["details"],
                    item["previous_hash"],
                    item["event_hash"],
                )
                for item in payload.get("audit_events", [])
            ],
            approved_at=(
                datetime.fromisoformat(payload["approved_at"])
                if payload.get("approved_at") else None
            ),
            approved_by=payload.get("approved_by"),
        )
        if candidate.config_hash != self.fingerprint(candidate.config):
            raise ValueError("stored candidate config hash mismatch")
        self._validate_audit_chain(candidate.audit_events)
        return candidate

    def exists(self, version: str) -> bool:
        self._validate_version(version)
        return self._path(version).exists()

    def _path(self, version: str) -> Path:
        return self.directory / f"{version}.json"

    @staticmethod
    def fingerprint(config: dict) -> str:
        canonical = json.dumps(
            config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _validate_version(cls, version: str) -> None:
        if not cls.VERSION_PATTERN.fullmatch(version):
            raise ValueError("invalid strategy version")

    @staticmethod
    def _json_default(value):
        if isinstance(value, Enum):
            return value.value
        if hasattr(value, "isoformat"):
            return value.isoformat()
        raise TypeError(f"cannot serialize {type(value).__name__}")

    @staticmethod
    def _validate_audit_chain(events: list[AuditEvent]) -> None:
        previous = ""
        for event in events:
            expected = AuditEvent.create(
                event.action,
                event.actor,
                event.details,
                previous_hash=previous,
                occurred_at=event.occurred_at,
            )
            if (
                event.previous_hash != previous
                or event.event_hash != expected.event_hash
            ):
                raise ValueError("strategy audit chain integrity check failed")
            previous = event.event_hash
