import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


@dataclass(slots=True, frozen=True)
class PilotDaySummary:
    date: date
    status: str
    run_count: int
    minimum_api_success_rate: float
    maximum_retry_rate: float
    maximum_exclusion_rate: float
    error_types: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class PilotReadiness:
    status: str
    required_days: int
    observed_days: int
    passing_days: int
    consecutive_passing_days: int
    days: list[PilotDaySummary]
    reasons: list[str]


class PilotHistoryRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def load_all(self) -> list[dict]:
        if not self.directory.exists():
            return []
        records = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["_file_mtime"] = path.stat().st_mtime
                records.append(payload)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return records


class PilotReadinessEvaluator:
    SEVERITY = {"PASS": 0, "PARTIAL": 1, "FAIL": 2}

    def __init__(self, required_days: int = 5) -> None:
        if required_days <= 0:
            raise ValueError("required_days must be greater than zero")
        self.required_days = required_days

    def evaluate(self, records: list[dict]) -> PilotReadiness:
        grouped = defaultdict(list)
        for record in records:
            grouped[datetime.fromisoformat(record["as_of"]).date()].append(record)
        days = [
            self._day(value, items)
            for value, items in sorted(grouped.items())
        ]
        consecutive = 0
        for item in reversed(days):
            if item.status != "PASS":
                break
            consecutive += 1
        reasons = []
        if len(days) < self.required_days:
            reasons.append(
                f"서로 다른 거래일 {len(days)}/{self.required_days}일 수집"
            )
        non_pass = [item for item in days if item.status != "PASS"]
        if non_pass:
            reasons.append(
                "미통과 거래일: "
                + ", ".join(
                    f"{item.date.isoformat()}({item.status})"
                    for item in non_pass
                )
            )
        ready = (
            len(days) >= self.required_days
            and consecutive >= self.required_days
        )
        return PilotReadiness(
            status="READY" if ready else "COLLECTING",
            required_days=self.required_days,
            observed_days=len(days),
            passing_days=sum(item.status == "PASS" for item in days),
            consecutive_passing_days=consecutive,
            days=days,
            reasons=reasons,
        )

    def _day(self, value, records):
        status = max(
            (record.get("status", "FAIL") for record in records),
            key=lambda item: self.SEVERITY.get(item, 2),
        )
        errors = Counter()
        for record in records:
            for message in record.get("fetch_failures", {}).values():
                errors[message.split(":", 1)[0]] += 1
        return PilotDaySummary(
            date=value,
            status=status,
            run_count=len(records),
            minimum_api_success_rate=min(
                record.get("api_success_rate", 0.0)
                for record in records
            ),
            maximum_retry_rate=max(
                record.get(
                    "retry_rate",
                    (
                        record.get("retry_count", 0)
                        / max(record.get("request_count", 0), 1)
                    ),
                )
                for record in records
            ),
            maximum_exclusion_rate=max(
                record.get("exclusion_rate", 1.0)
                for record in records
            ),
            error_types=dict(sorted(errors.items())),
        )
