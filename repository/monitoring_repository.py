import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from config.constants import OUTPUT_DIR


class MonitoringRepository:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or OUTPUT_DIR / "monitoring"

    def save(self, snapshot) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{snapshot.generated_at:%Y%m%dT%H%M%S}.json"
        path.write_text(
            json.dumps(
                asdict(snapshot),
                ensure_ascii=False,
                indent=2,
                default=self._json_default,
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _json_default(value):
        if isinstance(value, Enum):
            return value.value
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if hasattr(value, "value"):
            return value.value
        raise TypeError(f"cannot serialize {type(value).__name__}")
