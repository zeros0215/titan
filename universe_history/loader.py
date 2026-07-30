import csv
from datetime import date
from pathlib import Path

from domain.enums import MarketType
from universe_history.model import UniverseHistoryRecord


class UniverseHistoryLoader:
    REQUIRED_COLUMNS = {
        "code",
        "name",
        "market",
        "effective_from",
        "effective_to",
        "source_id",
    }

    def load(self, path: Path) -> list[UniverseHistoryRecord]:
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = set(reader.fieldnames or [])
            missing = self.REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError(
                    "universe history is missing columns: "
                    + ", ".join(sorted(missing))
                )
            records = []
            for line_number, row in enumerate(reader, start=2):
                try:
                    records.append(UniverseHistoryRecord(
                        code=row["code"].strip(),
                        name=row["name"].strip(),
                        market=MarketType(row["market"].strip().upper()),
                        effective_from=date.fromisoformat(
                            row["effective_from"].strip()
                        ),
                        effective_to=(
                            date.fromisoformat(row["effective_to"].strip())
                            if row["effective_to"].strip()
                            else None
                        ),
                        source_id=row["source_id"].strip(),
                    ))
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"invalid universe history row {line_number}: {error}"
                    ) from error
        return records
