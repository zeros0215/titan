import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from config.constants import OUTPUT_DIR
from operation.model import RunRecord, RunStatus


class RunRepository:
    def __init__(
        self,
        directory: Path | None = None,
        failure_directory: Path | None = None,
    ) -> None:
        self.directory = directory or OUTPUT_DIR / "runs"
        self.failure_directory = failure_directory or OUTPUT_DIR / "failures"

    def save(self, record: RunRecord) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{record.run_id}.json"
        payload = asdict(record)
        payload["status"] = record.status.value
        for key in ("operation_date", "started_at", "completed_at"):
            value = payload[key]
            payload[key] = value.isoformat() if value is not None else None
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def save_failures(self, record: RunRecord) -> Path | None:
        if not record.failures:
            return None
        self.failure_directory.mkdir(parents=True, exist_ok=True)
        path = self.failure_directory / f"{record.run_id}.json"
        path.write_text(
            json.dumps(
                {
                    "run_id": record.run_id,
                    "operation_date": record.operation_date.isoformat(),
                    "status": record.status.value,
                    "failures": record.failures,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def find(self, operation_date: datetime, strategy_version: str) -> RunRecord | None:
        if not self.directory.exists():
            return None
        for path in sorted(self.directory.glob("*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                datetime.fromisoformat(payload["operation_date"]) == operation_date
                and payload["strategy_version"] == strategy_version
            ):
                return self._deserialize(payload)
        return None

    def load_all(self) -> list[RunRecord]:
        if not self.directory.exists():
            return []
        records = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                records.append(
                    self._deserialize(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                )
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                continue
        return records

    @staticmethod
    def _deserialize(payload: dict) -> RunRecord:
        return RunRecord(
            run_id=payload["run_id"],
            operation_date=datetime.fromisoformat(payload["operation_date"]),
            strategy_version=payload["strategy_version"],
            status=RunStatus(payload["status"]),
            started_at=datetime.fromisoformat(payload["started_at"]),
            completed_at=(
                datetime.fromisoformat(payload["completed_at"])
                if payload.get("completed_at")
                else None
            ),
            selection_count=payload.get("selection_count", 0),
            observation_count=payload.get("observation_count", 0),
            validation_count=payload.get("validation_count", 0),
            skipped_validation_count=payload.get("skipped_validation_count", 0),
            warnings=payload.get("warnings", []),
            failures=payload.get("failures", []),
            forced=payload.get("forced", False),
        )
