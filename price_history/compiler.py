import csv
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from domain.enums import MarketType


@dataclass(slots=True, frozen=True)
class PriceRow:
    code: str
    name: str
    market: MarketType
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted: bool


class PriceHistoryLoader:
    REQUIRED_COLUMNS = {
        "code", "name", "market", "date", "open", "high", "low", "close",
        "volume", "adjusted",
    }

    def load(self, path: Path) -> list[PriceRow]:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = self.REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "price history is missing columns: "
                    + ", ".join(sorted(missing))
                )
            rows = []
            for line_number, row in enumerate(reader, start=2):
                try:
                    adjusted = row["adjusted"].strip().lower()
                    if adjusted not in {"true", "false"}:
                        raise ValueError("adjusted must be true or false")
                    rows.append(PriceRow(
                        code=row["code"].strip(),
                        name=row["name"].strip(),
                        market=MarketType(row["market"].strip().upper()),
                        date=date.fromisoformat(row["date"].strip()),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                        adjusted=adjusted == "true",
                    ))
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"invalid price history row {line_number}: {error}"
                    ) from error
        return rows


class PriceHistoryCompiler:
    CODE_PATTERN = re.compile(r"^[0-9A-Z]{6}$")
    PROVENANCE_FIELDS = (
        "source_name", "source_type", "dataset_id", "evidence_url",
        "acquired_at", "source_complete",
    )

    def compile(
        self,
        rows: list[PriceRow],
        source_manifest: dict,
        coverage_start: date,
        coverage_end: date,
        output_dir: Path,
        input_path: Path,
    ) -> dict:
        self._validate(rows, source_manifest, coverage_start, coverage_end)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row.code].append(row)
        output_dir.mkdir(parents=True, exist_ok=True)
        for code, items in grouped.items():
            ordered = sorted(items, key=lambda item: item.date)
            first = ordered[0]
            payload = {
                "code": code,
                "name": first.name,
                "market": first.market.value,
                "adjusted_prices": True,
                "source_id": source_manifest["dataset_id"],
                "candles": [
                    {
                        "date": datetime.combine(
                            item.date, datetime.min.time()
                        ).isoformat(),
                        "open": item.open,
                        "high": item.high,
                        "low": item.low,
                        "close": item.close,
                        "volume": item.volume,
                    }
                    for item in ordered
                ],
            }
            (output_dir / f"{code}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        manifest = {
            "schema_version": 1,
            "price_history_complete": True,
            "adjusted_prices": True,
            "coverage_start": coverage_start.isoformat(),
            "coverage_end": coverage_end.isoformat(),
            "stock_count": len(grouped),
            "row_count": len(rows),
            "input_sha256": self.file_sha256(input_path),
            "source": source_manifest,
            "compiled_at": datetime.now().astimezone().isoformat(),
        }
        (output_dir / "price_history_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    def _validate(self, rows, manifest, start, end):
        if end < start:
            raise ValueError("coverage_end must not be before coverage_start")
        if not rows:
            raise ValueError("price history is empty")
        missing = [
            key for key in self.PROVENANCE_FIELDS
            if key not in manifest or manifest[key] in {"", None, False}
        ]
        if missing:
            raise ValueError(
                "source manifest is incomplete: " + ", ".join(missing)
            )
        seen = set()
        for row in rows:
            if not self.CODE_PATTERN.fullmatch(row.code):
                raise ValueError(f"invalid stock code: {row.code}")
            if not row.adjusted:
                raise ValueError(
                    f"unadjusted price row is not allowed: {row.code} {row.date}"
                )
            if not start <= row.date <= end:
                raise ValueError(f"price date outside declared coverage: {row.date}")
            if min(row.open, row.high, row.low, row.close) <= 0:
                raise ValueError(f"non-positive OHLC: {row.code} {row.date}")
            if row.high < max(row.open, row.low, row.close):
                raise ValueError(f"invalid high price: {row.code} {row.date}")
            if row.low > min(row.open, row.high, row.close):
                raise ValueError(f"invalid low price: {row.code} {row.date}")
            if row.volume < 0:
                raise ValueError(f"negative volume: {row.code} {row.date}")
            key = (row.code, row.date)
            if key in seen:
                raise ValueError(f"duplicate stock date: {row.code} {row.date}")
            seen.add(key)
        if min(row.date for row in rows) > start:
            raise ValueError("rows do not reach declared coverage_start")
        if max(row.date for row in rows) < end:
            raise ValueError("rows do not reach declared coverage_end")

    @staticmethod
    def file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
