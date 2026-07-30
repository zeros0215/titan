import json
from datetime import datetime
from pathlib import Path

from strategy_gate.model import AuditEvent, CandidateStatus


class StrategyGateService:
    def __init__(self, repository, gate) -> None:
        self.repository = repository
        self.gate = gate

    def evaluate(
        self,
        version: str,
        baseline_path: Path,
        candidate_path: Path,
        actor: str,
    ):
        candidate = self.repository.load(version)
        if candidate.status is CandidateStatus.APPROVED:
            raise ValueError("approved candidate cannot be re-evaluated")
        baseline = self._load_result(baseline_path)
        result = self._load_result(candidate_path)
        if baseline.get("strategy_version") != candidate.base_version:
            raise ValueError("baseline result version does not match candidate base")
        if result.get("strategy_version") != candidate.candidate_version:
            raise ValueError("candidate result version does not match proposal")
        if result.get("strategy_config_hash") != candidate.config_hash:
            raise ValueError("candidate result config hash does not match proposal")
        comparison, checks = self.gate.evaluate(baseline, result)
        candidate.comparison = comparison
        candidate.gate_checks = checks
        candidate.status = (
            CandidateStatus.PASSED
            if comparison["passed"]
            else CandidateStatus.FAILED
        )
        candidate.audit_events.append(AuditEvent.create(
            "EVALUATED",
            self._actor(actor),
            f"gate={candidate.status.value}",
            previous_hash=candidate.audit_events[-1].event_hash,
        ))
        self.repository.save(candidate)
        return candidate

    def approve(self, version: str, actor: str, note: str):
        candidate = self.repository.load(version)
        if candidate.status is not CandidateStatus.PASSED:
            raise ValueError("only a PASSED candidate can be approved")
        if not note.strip():
            raise ValueError("approval note is required")
        now = datetime.now()
        candidate.status = CandidateStatus.APPROVED
        candidate.approved_at = now
        candidate.approved_by = self._actor(actor)
        candidate.audit_events.append(AuditEvent.create(
            "APPROVED",
            candidate.approved_by,
            note.strip(),
            previous_hash=candidate.audit_events[-1].event_hash,
            occurred_at=now,
        ))
        self.repository.save(candidate)
        return candidate

    @staticmethod
    def _load_result(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("folds"), list):
            raise ValueError(f"invalid walk-forward result: {path}")
        return payload

    @staticmethod
    def _actor(actor: str) -> str:
        if not actor.strip():
            raise ValueError("actor is required")
        return actor.strip()
