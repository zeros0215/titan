"""Point-in-time aware stock-universe repository."""

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

from domain.enums import MarketType
from domain.stock import Stock
from repository.universe_snapshot import UniverseCoverage, UniverseSnapshot


class StockRepository:
    def __init__(self, market_dir: Path | None = None) -> None:
        self.market_dir = market_dir or (
            Path(__file__).resolve().parent.parent / "resources" / "market"
        )

    def get_all(self) -> list[Stock]:
        stocks = []
        for file_name in ("kospi.csv", "kosdaq.csv"):
            stocks.extend(self._load_csv(file_name))
        return stocks

    def get_as_of(self, as_of: datetime) -> UniverseSnapshot:
        source = self.get_all()
        active = []
        before = 0
        after = 0
        for stock in source:
            if stock.effective_from is not None and as_of < stock.effective_from:
                before += 1
                continue
            if stock.effective_to is not None and as_of > stock.effective_to:
                after += 1
                continue
            active.append(stock)

        dated = sum(stock.effective_from is not None for stock in source)
        complete = self._point_in_time_complete(as_of)
        if complete and dated == len(source):
            coverage = UniverseCoverage.COMPLETE
        elif dated:
            coverage = UniverseCoverage.PARTIAL
        else:
            coverage = UniverseCoverage.UNKNOWN
        return UniverseSnapshot(
            as_of=as_of,
            stocks=active,
            source_count=len(source),
            dated_count=dated,
            excluded_before_listing=before,
            excluded_after_delisting=after,
            coverage=coverage,
            point_in_time_complete=complete,
        )

    def _load_csv(self, file_name: str) -> list[Stock]:
        path = self.market_dir / file_name
        with path.open(encoding="utf-8") as stream:
            return [
                Stock(
                    code=row["code"],
                    name=row["name"],
                    market=MarketType(row["market"]),
                    effective_from=self._date(
                        row.get("effective_from") or row.get("listed_at")
                    ),
                    effective_to=self._date(
                        row.get("effective_to") or row.get("delisted_at")
                    ),
                )
                for row in csv.DictReader(stream)
            ]

    def _point_in_time_complete(self, as_of: datetime) -> bool:
        path = self.market_dir / "universe_manifest.json"
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if payload.get("point_in_time_complete") is not True:
            return False
        coverage_start = self._date(payload.get("coverage_start"))
        coverage_end = self._date(payload.get("coverage_end"))
        if coverage_start is not None and as_of < coverage_start:
            return False
        if coverage_end is not None and as_of > coverage_end.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        ):
            return False
        if payload.get("schema_version") == 1:
            if payload.get("source_complete") is not True:
                return False
            if payload.get("source_manifest_coverage_matches") is not True:
                return False
            if payload.get("provenance_complete") is not True:
                return False
            for name, expected in payload.get("compiled_files", {}).items():
                target = self.market_dir / name
                if not target.exists() or self._sha256(target) != expected:
                    return False
            if set(payload.get("compiled_files", {})) != {
                "kospi.csv",
                "kosdaq.csv",
            }:
                return False
        return True

    @staticmethod
    def _date(value: str | None) -> datetime | None:
        value = (value or "").strip()
        return datetime.fromisoformat(value) if value else None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
