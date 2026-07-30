import json
from pathlib import Path

from config.constants import OUTPUT_DIR
from repository.universe_snapshot import UniverseSnapshot


class UniverseRepository:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or OUTPUT_DIR / "universe"

    def save(self, snapshot: UniverseSnapshot) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{snapshot.as_of:%Y%m%dT%H%M%S}.json"
        payload = {
            "as_of": snapshot.as_of.isoformat(),
            "coverage": snapshot.coverage.value,
            "point_in_time_complete": snapshot.point_in_time_complete,
            "source_count": snapshot.source_count,
            "active_count": snapshot.active_count,
            "dated_count": snapshot.dated_count,
            "unknown_date_count": snapshot.unknown_date_count,
            "excluded_before_listing": snapshot.excluded_before_listing,
            "excluded_after_delisting": snapshot.excluded_after_delisting,
            "codes": [stock.code for stock in snapshot.stocks],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path
