import json
from datetime import datetime
from pathlib import Path

from config.constants import OUTPUT_DIR
from data.quality import DataQualitySummary


class DataQualityRepository:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or OUTPUT_DIR / "quality"

    def save(self, selected_at: datetime, summary: DataQualitySummary) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{selected_at:%Y%m%dT%H%M%S}.json"
        payload = {
            "selected_at": selected_at.isoformat(),
            "total_count": summary.total_count,
            "valid_count": summary.valid_count,
            "warning_count": summary.warning_count,
            "excluded_count": summary.excluded_count,
            "issues_by_code": summary.issues_by_code,
            "issues_by_stock": {
                code: [
                    {
                        "code": issue.code,
                        "severity": issue.severity.value,
                        "message": issue.message,
                    }
                    for issue in issues
                ]
                for code, issues in summary.issues_by_stock.items()
            },
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_all(self) -> list[dict]:
        if not self.directory.exists():
            return []
        records = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return records
