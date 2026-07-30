import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


class QualityQuarantinePolicy:
    def __init__(self, intervals_by_code=None):
        self.intervals_by_code = intervals_by_code or {}

    @classmethod
    def from_file(cls, path: Path):
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        grouped = defaultdict(list)
        for item in payload:
            grouped[item["code"]].append((
                datetime.fromisoformat(item["start"]),
                datetime.fromisoformat(item["end"]),
            ))
        return cls(dict(grouped))

    def allows(self, code: str, as_of: datetime) -> bool:
        return not any(
            start <= as_of <= end
            for start, end in self.intervals_by_code.get(code, [])
        )

    def filter(self, analyses, as_of: datetime):
        return [
            item for item in analyses
            if self.allows(item.code, as_of)
        ]
